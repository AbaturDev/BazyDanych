import oracledb


class BufferFlusher:
    def __init__(self, config):
        self.config = config

    def flush(self):
        connection = oracledb.connect(user="system",
                                      password=self.config.admin_password,
                                      dsn=self.config.dsn)
        try:
            cursor = connection.cursor()

            cursor.execute("ALTER SYSTEM CHECKPOINT")
            cursor.execute("ALTER SYSTEM FLUSH BUFFER_CACHE")
            cursor.execute("ALTER SYSTEM FLUSH SHARED_POOL")

            cursor.close()
        finally:
            connection.close()

        print("  buffers flushed (checkpoint, buffer cache, shared pool)")
