import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io


def enviar_relatorio_email(
    smtp_host: str,
    smtp_port: int,
    usar_ssl: bool,
    remetente: str,
    senha: str,
    destinatarios: list[str],
    pdf_bytes: bytes | io.BytesIO,
    nome_arquivo: str,
    data_ref: str,
    resumo_compliance: str = "",
) -> None:
    if isinstance(pdf_bytes, io.BytesIO):
        pdf_bytes.seek(0)
        conteudo_pdf = pdf_bytes.read()
    else:
        conteudo_pdf = pdf_bytes

    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = f"VIGIA — Relatório Mensal IAJA {data_ref}"

    corpo = (
        f"Prezados,\n\n"
        f"Segue em anexo o Relatório Executivo de Investimentos do IAJA referente a {data_ref}.\n\n"
        f"{resumo_compliance}\n\n"
        f"Este e-mail foi gerado automaticamente pelo sistema VIGIA.\n\n"
        f"Atenciosamente,\n"
        f"Sistema VIGIA — Análise de Investimentos IAJA"
    )
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

    parte = MIMEBase('application', 'octet-stream')
    parte.set_payload(conteudo_pdf)
    encoders.encode_base64(parte)
    parte.add_header('Content-Disposition', f'attachment; filename="{nome_arquivo}"')
    msg.attach(parte)

    context = ssl.create_default_context()
    if usar_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(remetente, senha)
            server.sendmail(remetente, destinatarios, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(remetente, senha)
            server.sendmail(remetente, destinatarios, msg.as_string())
