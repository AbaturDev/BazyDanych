from app.buffer_flusher import BufferFlusher
from app.container_control import ContainerControl


class DatabasePreparation:
    def __init__(self, config):
        self.config = config
        self.container_control = ContainerControl(config.container_name)
        self.buffer_flusher = BufferFlusher(config)

    def prepare(self):
        self.container_control.recreate_database()

        # 2. TODO (B, step 5): check state against the reference
        #    (row counts, MAX(ID), checksums, SYSDATE = 2026-11-21).
        #    Raise an exception if the state does not match - the run will not start.

        self.buffer_flusher.flush()
        self.container_control.drop_os_cache()
