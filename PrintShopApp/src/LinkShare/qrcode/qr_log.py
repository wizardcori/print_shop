import os
from Common.paths import QRCODE_LOG_FULLPATH
from Common.log import SubLoggerManager


class QrcodeLog(SubLoggerManager):
    """QR 코드 생성, 스캔 및 처리 관련 로그를 전담하는 매니저 클래스 (클래스 메서드 지원)"""
    
    _instance = None

    @classmethod
    def _get_logger(cls):
        """공용 로거 인스턴스를 반환하는 싱글톤 내부 메서드"""
        if cls._instance is None:
            cls._instance = cls(
                log_file=os.path.join(QRCODE_LOG_FULLPATH),
                flush_interval=5.0,
                module_name="QrcodeModule",
                default_tag="QRCODE"
            )
        return cls._instance

    def __init__(
        self, 
        log_file=os.path.join(QRCODE_LOG_FULLPATH), 
        flush_interval=5.0, 
        module_name="QrcodeModule", 
        default_tag="QRCODE", 
        individual_format=None, 
        global_format=None
    ):
        super().__init__(
            log_file=log_file, 
            flush_interval=flush_interval, 
            module_name=module_name, 
            default_tag=default_tag, 
            individual_format=individual_format, 
            global_format=global_format
        )

    @classmethod
    def log_qrcode_generated(cls, data: str, tag=None):
        """QR 코드 생성 성공 시 호출하는 클래스 로그 메서드[cite: 1]"""
        cls._get_logger().info(f"QR Code Generated Successfully | Data: {data}", tag=tag)

    @classmethod
    def log_qrcode_scanned(cls, result: str, success: bool = True, tag=None):
        """QR 코드 스캔(인식) 결과 클래스 로그 메서드[cite: 1]"""
        logger = cls._get_logger()
        if success:
            logger.info(f"QR Code Scanned Successfully | Result: {result}", tag=tag)
        else:
            logger.error(f"QR Code Scan Failed | Reason: {result}", tag=tag)

    @classmethod
    def log_qrcode_error(cls, error_message: str, tag=None):
        """QR 코드 처리 중 발생한 에러 클래스 로그 메서드[cite: 1]"""
        cls._get_logger().error(f"QR Code Processing Error | Details: {error_message}", tag=tag)

    @classmethod
    def log_qrcode_validation(cls, data: str, is_valid: bool, tag=None):
        """QR 코드 데이터 유효성 검증 결과 클래스 로그 메서드[cite: 1]"""
        logger = cls._get_logger()
        if is_valid:
            logger.info(f"QR Code Validation Passed | Data: {data}", tag=tag)
        else:
            logger.warning(f"QR Code Validation Failed | Data: {data}", tag=tag)