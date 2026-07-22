"""
Фоновая (detached-subprocess) команда авторазвёртывания портала на
удалённой VM по SSH. Запускается из accounts.views.portal_deploy через
subprocess.Popen, читает spec-файл (SSH-креды + .env-конфиг + сборочный
url репо), выполняет шаги по SSH (paramiko) и пишет прогресс в DeployJob.

Безопасность: spec-файл (с секретами) удаляется по завершении; в лог
DeployJob не попадают ни пароли/ключи, ни содержимое .env, ни clone-url
с токеном - только описания шагов и безопасный хвост вывода команд.
"""

import io
import json
import os
import shlex

import paramiko
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import DeployJob

DEPLOY_DIR_TMPL = "/opt/{org}-portal"


def _load_key(key_str, passphrase):
    for key_cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(key_str), password=passphrase or None)
        except Exception:
            continue
    raise RuntimeError("Не удалось разобрать приватный ключ (ожидается ed25519/rsa/ecdsa).")


class Command(BaseCommand):
    help = "Развернуть портал на удалённой VM по SSH (запускается из консоли ССОД)."

    def add_arguments(self, parser):
        parser.add_argument("job_uuid")
        parser.add_argument("spec_file")

    def handle(self, *args, **opts):
        spec_path = opts["spec_file"]
        try:
            job = DeployJob.objects.get(uuid=opts["job_uuid"])
        except DeployJob.DoesNotExist:
            self._remove(spec_path)
            return

        try:
            with open(spec_path, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
        except Exception as e:
            job.status = DeployJob.Status.FAILED
            job.append_log(f"Не удалось прочитать spec-файл: {e}")
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at", "updated_at"])
            self._remove(spec_path)
            return

        job.status = DeployJob.Status.RUNNING
        job.save(update_fields=["status", "updated_at"])
        job.append_log("=== Старт развёртывания ===")

        try:
            self._deploy(job, spec)
            job.status = DeployJob.Status.SUCCESS
            job.append_log("=== Развёртывание завершено успешно ===")
        except Exception as e:
            job.status = DeployJob.Status.FAILED
            job.append_log(f"ОШИБКА: {e}")
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at", "updated_at"])
            self._remove(spec_path)  # секреты не остаются на диске

    @staticmethod
    def _remove(path):
        try:
            os.remove(path)
        except OSError:
            pass

    def _deploy(self, job, spec):
        ssh_spec = spec["ssh"]
        env_lines = spec["env"]            # dict KEY->VALUE
        clone = spec["clone"]              # {mode: ssh|https, url, deploy_key?} - НЕ логировать
        org = spec["org_code"]
        deploy_dir = DEPLOY_DIR_TMPL.format(org=org)
        sudo_password = ssh_spec.get("sudo_password") or ""

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": job.target_host,
            "port": job.target_port,
            "username": job.target_user,
            "timeout": 25,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if ssh_spec.get("private_key"):
            connect_kwargs["pkey"] = _load_key(ssh_spec["private_key"], ssh_spec.get("key_passphrase"))
        else:
            connect_kwargs["password"] = ssh_spec.get("password") or ""

        job.append_log(f"Подключаюсь по SSH к {job.target_host}:{job.target_port} как {job.target_user}…")
        ssh.connect(**connect_kwargs)
        transport = ssh.get_transport()
        host_key = transport.get_remote_server_key()
        fp = ":".join(f"{b:02x}" for b in host_key.get_fingerprint())
        job.append_log(f"Подключено. Отпечаток хоста ({host_key.get_name()}): {fp}")

        def run(cmd, use_sudo=False, log_cmd=None, timeout=900):
            shell_cmd = cmd
            if use_sudo:
                if sudo_password:
                    shell_cmd = f"echo {shlex.quote(sudo_password)} | sudo -S bash -lc {shlex.quote(cmd)}"
                else:
                    shell_cmd = f"sudo bash -lc {shlex.quote(cmd)}"
            job.append_log(f"$ {log_cmd if log_cmd is not None else cmd}")
            _in, _out, _err = ssh.exec_command(shell_cmd, timeout=timeout)
            out = _out.read().decode("utf-8", "replace")
            err = _err.read().decode("utf-8", "replace")
            rc = _out.channel.recv_exit_status()
            tail = (out or err).strip().splitlines()[-8:]
            for line in tail:
                job.append_log("  " + line)
            if rc != 0:
                raise RuntimeError(f"Команда завершилась с кодом {rc}: {(err or out)[:400]}")
            return out

        # 1. Базовые пакеты + Docker
        job.append_log("--- Проверка/установка Docker и git ---")
        run("command -v git >/dev/null || (apt-get update && apt-get install -y git ca-certificates openssl)", use_sudo=True)
        run("command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)", use_sudo=True)
        run("docker compose version >/dev/null 2>&1 || (apt-get update && apt-get install -y docker-compose-plugin)", use_sudo=True)

        # 2. Клонирование репозитория (url/ключ НЕ логируем)
        job.append_log("--- Клонирование репозитория портала ---")
        if clone.get("mode") == "ssh":
            # read-only deploy-key: заливаем во временный файл на VM, клонируем
            # по git@github.com:..., удаляем ключ сразу же (даже при ошибке).
            tmp_key = f"/tmp/{org}-deploy-key"
            sftp = ssh.open_sftp()
            with sftp.open(tmp_key, "w") as fh:
                fh.write(clone["deploy_key"])
            sftp.chmod(tmp_key, 0o600)
            sftp.close()
            git_ssh = (
                f"GIT_SSH_COMMAND='ssh -i {tmp_key} -o IdentitiesOnly=yes "
                "-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.ssh/known_hosts'"
            )
            run(
                f"install -m 600 {shlex.quote(tmp_key)} /root/.portal-deploy-key && rm -f {shlex.quote(tmp_key)}; "
                f"mkdir -p /root/.ssh; rm -rf {shlex.quote(deploy_dir)}; "
                f"{git_ssh} git clone --depth 1 {shlex.quote(clone['url'])} {shlex.quote(deploy_dir)}; "
                "rc=$?; rm -f /root/.portal-deploy-key; exit $rc",
                use_sudo=True,
                log_cmd=f"git clone <deploy-key> {deploy_dir}",
            )
        else:
            run(
                f"rm -rf {shlex.quote(deploy_dir)} && git clone --depth 1 {shlex.quote(clone['url'])} {shlex.quote(deploy_dir)}",
                use_sudo=True,
                log_cmd=f"git clone <repo> {deploy_dir}",
            )

        # 3. Заливаем .env через SFTP в /tmp (без логирования содержимого), затем sudo-переносим
        job.append_log("--- Запись .env ---")
        env_text = "".join(f"{k}={v}\n" for k, v in env_lines.items())
        tmp_env = f"/tmp/{org}-portal.env"
        sftp = ssh.open_sftp()
        with sftp.open(tmp_env, "w") as fh:
            fh.write(env_text)
        sftp.chmod(tmp_env, 0o600)
        sftp.close()
        run(f"install -m 600 {shlex.quote(tmp_env)} {shlex.quote(deploy_dir)}/.env && rm -f {shlex.quote(tmp_env)}", use_sudo=True)

        # 4. Self-signed сертификат (nginx/certs)
        job.append_log("--- Генерация self-signed сертификата ---")
        cert_cmd = (
            f"cd {shlex.quote(deploy_dir)} && mkdir -p nginx/certs && "
            "test -f nginx/certs/portal.crt || openssl req -x509 -nodes -days 3650 -newkey rsa:2048 "
            "-keyout nginx/certs/portal.key -out nginx/certs/portal.crt "
            f"-subj '/C=RU/O={org}/CN=portal.local' -addext 'subjectAltName=DNS:portal.local'"
        )
        run(cert_cmd, use_sudo=True)

        # 5. Сборка и запуск (образ сам применяет миграции в CMD)
        job.append_log("--- docker compose up -d --build (может занять несколько минут) ---")
        run(f"cd {shlex.quote(deploy_dir)} && docker compose up -d --build", use_sudo=True, timeout=1800)

        # 6. Короткая проверка, что контейнеры поднялись
        job.append_log("--- Статус контейнеров ---")
        run(f"cd {shlex.quote(deploy_dir)} && docker compose ps", use_sudo=True)

        ssh.close()
        job.append_log(f"Портал развёрнут в {deploy_dir} на {job.target_host}.")
