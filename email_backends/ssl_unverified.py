import ssl
import smtplib
from django.core.mail.backends.smtp import EmailBackend
 
class SSLUnverifiedEmailBackend(EmailBackend):
    def open(self):
        if self.connection:
            return False
        
        # 创建不验证证书的SSL上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            # 对于SSL连接，使用SMTP_SSL，但注意SMTP_SSL的初始化参数不同
            if self.use_ssl:
                self.connection = smtplib.SMTP_SSL(
                    host=self.host, 
                    port=self.port, 
                    context=ssl_context,
                    timeout=self.timeout
                )
            else:
                self.connection = smtplib.SMTP(
                    host=self.host, 
                    port=self.port, 
                    timeout=self.timeout
                )
                if self.use_tls:
                    self.connection.starttls(context=ssl_context)
            
            # 登录部分
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise