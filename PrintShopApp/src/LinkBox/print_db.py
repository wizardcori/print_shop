"""Print operations database repository."""
from Common.base_db import BaseDb
from .setting.print_fare_settings import PrintFareConfig


class PrintDatabase(BaseDb):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fare_config = PrintFareConfig()

    def _initialize(self):
        super()._initialize()
        with self._lock, self._connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS print_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    client_info TEXT,
                    operator_info TEXT,
                    printer_name TEXT,
                    color_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    requested_pages INTEGER NOT NULL DEFAULT 0,
                    actual_pages INTEGER NOT NULL DEFAULT 0,
                    unit_price REAL NOT NULL DEFAULT 0.0,
                    total_price REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL,
                    spooler_job_id INTEGER,
                    counter_before INTEGER,
                    counter_after INTEGER,
                    error_message TEXT
                );
            ''')

    def get_print_price(self, color_type, paper_size, item_name="TEXT ONLY"):
        """PrintFareConfig를 참조하여 color_type과 paper_size에 해당하는 요금을 조회합니다."""
        color = str(color_type).upper()
        size = str(paper_size).upper()
        
        is_color = "COLOR" in color or "COLORED" in color
        is_long = "LONG" in size or "F4" in size or "FOLIO" in size
        
        # PrintFareConfig의 kind 코드 매핑
        if is_color:
            kind = "print_colored_long" if is_long else "print_colored_short"
        else:
            kind = "print_bw_long" if is_long else "print_bw_short"
            
        items = self.fare_config.get_items(kind=kind, active_only=True)
        
        # 일치하는 item_name의 가격 반환
        for item in items:
            if item["item_name"].upper() == str(item_name).upper():
                return float(item["price"])
                
        # 일치하는 항목이 없을 경우 해당 카테고리의 첫 번째 활성 항목 가격 반환
        if items:
            return float(items[0]["price"])
            
        return 0.0

    def save_print_log(self, record):
        fields = ('timestamp', 'client_info', 'operator_info', 'printer_name',
                  'color_type', 'paper_size', 'requested_pages', 'actual_pages',
                  'unit_price', 'total_price', 'status', 'spooler_job_id',
                  'counter_before', 'counter_after', 'error_message')
        values = [record.get(field) for field in fields]
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO print_logs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                values,
            )
            return cursor.lastrowid

    def load_print_logs(self, limit=100):
        with self._lock, self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM print_logs ORDER BY id DESC LIMIT ?', (int(limit),)
            )]