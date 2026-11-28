import subprocess
import time

READY_MESSAGE = "DATABASE IS READY TO USE!"
READY_TIMEOUT_SECONDS = 900


class ContainerControl:
    def __init__(self, container_name):
        self.container_name = container_name

    def recreate_database(self):
        start = time.perf_counter()

        print("  docker compose down -v (removing database and data)...", flush=True)
        self.run_command(["docker", "compose", "down", "-v"])

        print("  docker compose up -d (creating database, loading data)...", flush=True)
        self.run_command(["docker", "compose", "up", "-d"])
        self.wait_until_ready()

        print(f"  database ready after {time.perf_counter() - start:.0f} s")

    def wait_until_ready(self):
        deadline = time.time() + READY_TIMEOUT_SECONDS
        while time.time() < deadline:
            logs = self.run_command(["docker", "logs", self.container_name])
            if READY_MESSAGE in logs:
                return
            time.sleep(5)
        raise Exception(f"Database not ready after {READY_TIMEOUT_SECONDS} s. "
                        f"Check: docker logs {self.container_name}")

    def drop_os_cache(self):
        self.run_command(["docker", "run", "--rm", "--privileged", "alpine",
                          "sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
        print("  OS file cache dropped")

    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Command failed: {' '.join(command)}\n{result.stderr}")
        return result.stdout + result.stderr
