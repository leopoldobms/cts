import pymysql
from packages.common.secret_manager import secret_manager
from packages.common.constants import DB_TABLE_SCHEMA, DB_PORT


class Database:

    connection = None
    cursor = None
    transaction = None

    def __init__(self, transaction=None):
        host = secret_manager.get_secret("DB_HOSTNAME")
        user = secret_manager.get_secret("DB_USER")
        password = secret_manager.get_secret("DB_PASSWORD")
        db_name = DB_TABLE_SCHEMA
        port = DB_PORT

        self.connection = pymysql.connect(
            host, user, password, db_name, port, charset="utf8", use_unicode=True
        )
        self.cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        self.transaction = transaction

    """ function to select on database
        join variable must be a list of joins, ex: ["JOIN cts_response cts ON ar.cts_response_id = cts.id"]
        where variable must be a dict of field:value, ex: {"ar.code": 70,"ar.acquirer_id": 1}"""

    def select(self, fields, table, join=None, where=None, group_by=None):
        params = ()
        query = "SELECT " + fields + " FROM " + table + " "
        if isinstance(join, list):
            query += " ".join(join)
        if isinstance(where, dict):
            query += " WHERE (" + " = %s ) AND (".join(where.keys()) + " = %s)"
            params = tuple(where.values())
        if isinstance(group_by, str):
            query += " GROUP BY %s"
            params = tuple([*where.values(), group_by])

        return False if not self.__execute(query, params) else self.cursor.fetchall()

    def insert(self, values, table):
        qtd = len(values)
        param = tuple(values.values())
        str_bind = "(" + (",".join(["%s"] * qtd)) + ")"
        str_attr = "(" + (",".join([k for k in values.keys()])) + ")"
        query = "INSERT INTO " + table + str_attr + " VALUES " + str_bind
        if not self.__execute(query, param):
            return False
        if not self.transaction:
            self.connection.commit()
        return self.cursor.lastrowid

    def __execute(self, query, param=None):
        self.cursor.execute(query, param)
        return True
