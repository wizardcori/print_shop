class CurrentUserSession:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CurrentUserSession, cls).__new__(cls, *args, **kwargs)
            cls._instance._init_session()
        return cls._instance

    def _init_session(self):
        self.is_logged_in = False
        self.username = ""
        self.authority = ""
        self.privilege = {}  # 또는 list 형태 등급별 권한 관리

    def login(self, username, authority, privilege=None):
        """로그인 성공 시 세션 정보를 업데이트합니다."""
        self.is_logged_in = True
        self.username = username
        self.authority = authority
        self.privilege = privilege or {}

    def logout(self):
        """로그아웃 시 세션 정보를 초기화합니다."""
        self._init_session()

    def has_privilege(self, key):
        """특정 기능/특권(privilege)을 가지고 있는지 확인"""
        return self.privilege.get(key, False)

    def get_authority(self):
        return self.authority

    def is_admin_user(self):
        if self.get_authority() == 1:
            return True
        return False

    def get_username(self):
        return self.username

# 싱글톤 인스턴스
current_user_session = CurrentUserSession()


def get_username():
    """현재 로그인된 사용자 세션 인스턴스를 반환합니다."""
    return current_user_session.get_username()    