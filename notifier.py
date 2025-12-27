"""
Email notification system for Opera Ticket Monitor
"""
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from config import EmailConfig
from models import Performance, TicketStatus

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles sending email notifications"""

    def __init__(self, config: EmailConfig):
        self.config = config

    def _create_performance_html(self, performance: Performance) -> str:
        """Create HTML representation of a performance"""
        status_colors = {
            TicketStatus.AVAILABLE: "#28a745",  # green
            TicketStatus.LIMITED: "#ffc107",    # yellow
            TicketStatus.SOLD_OUT: "#dc3545",   # red
            TicketStatus.UNKNOWN: "#6c757d",    # gray
        }

        status_labels = {
            TicketStatus.AVAILABLE: "DOSTĘPNE",
            TicketStatus.LIMITED: "OSTATNIE BILETY",
            TicketStatus.SOLD_OUT: "WYPRZEDANE",
            TicketStatus.UNKNOWN: "Sprawdź dostępność",
        }

        status_color = status_colors.get(performance.status, "#6c757d")
        status_label = status_labels.get(performance.status, "Nieznany")

        date_display = performance.date_str or "Data do potwierdzenia"
        time_display = performance.time or ""

        html = f"""
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; background: #f9f9f9;">
            <h3 style="margin: 0 0 8px 0; color: #333;">🎭 {performance.opera_name}</h3>
            <p style="margin: 4px 0; color: #666;">
                <strong>🏛️ {performance.opera_house}</strong> ({performance.city})
            </p>
            <p style="margin: 4px 0; color: #666;">
                📅 {date_display} {time_display}
            </p>
            <p style="margin: 8px 0;">
                <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;">
                    {status_label}
                </span>
            </p>
            {f'<a href="{performance.ticket_url}" style="display: inline-block; background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; margin-top: 8px;">🎫 Kup bilety</a>' if performance.ticket_url else ''}
        </div>
        """
        return html

    def _create_email_content(
        self, performances: list[Performance], is_new: bool = True
    ) -> tuple[str, str]:
        """Create email subject and body"""
        if is_new:
            subject = f"🎭 NOWE BILETY! {len(performances)} {'spektakl' if len(performances) == 1 else 'spektakli'} Halka/Straszny Dwór"
        else:
            subject = f"🎭 Aktualizacja dostępności biletów - Halka/Straszny Dwór"

        # Group by opera
        halka_performances = [p for p in performances if "Halka" in p.opera_name]
        straszny_dwor_performances = [
            p for p in performances if "Straszny" in p.opera_name
        ]

        performances_html = ""

        if halka_performances:
            performances_html += "<h2 style='color: #333;'>🎵 Halka</h2>"
            for perf in halka_performances:
                performances_html += self._create_performance_html(perf)

        if straszny_dwor_performances:
            performances_html += "<h2 style='color: #333;'>🏰 Straszny Dwór</h2>"
            for perf in straszny_dwor_performances:
                performances_html += self._create_performance_html(perf)

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
                <h1 style="margin: 0;">🎭 Opera Ticket Monitor</h1>
                <p style="margin: 8px 0 0 0; opacity: 0.9;">Znaleziono bilety na polskie opery!</p>
            </div>

            <div style="background: white; padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
                {performances_html}

                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

                <p style="color: #999; font-size: 12px; text-align: center;">
                    Ten email został wygenerowany automatycznie przez Opera Ticket Monitor.<br>
                    Czas sprawdzenia: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </p>
            </div>
        </body>
        </html>
        """

        # Plain text version
        text_body = f"""
OPERA TICKET MONITOR - Znaleziono bilety!

"""
        for perf in performances:
            text_body += f"""
{perf.opera_name}
{perf.opera_house} ({perf.city})
Data: {perf.date_str or 'Do potwierdzenia'} {perf.time}
Link: {perf.ticket_url or 'Sprawdź stronę teatru'}
---
"""

        return subject, html_body, text_body

    def send_notification(
        self, performances: list[Performance], is_new: bool = True
    ) -> bool:
        """Send email notification about found performances"""
        if not performances:
            logger.info("No performances to notify about")
            return True

        if not self.config.sender_email or not self.config.sender_password:
            logger.warning(
                "Email credentials not configured. "
                "Set SENDER_EMAIL and SENDER_PASSWORD environment variables."
            )
            # Still log the performances
            self._log_performances(performances)
            return False

        try:
            subject, html_body, text_body = self._create_email_content(
                performances, is_new
            )

            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.config.sender_email
            message["To"] = ", ".join(self.config.recipient_emails)

            # Attach both plain text and HTML versions
            message.attach(MIMEText(text_body, "plain", "utf-8"))
            message.attach(MIMEText(html_body, "html", "utf-8"))

            # Send email
            context = ssl.create_default_context()

            with smtplib.SMTP(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.config.sender_email, self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    self.config.recipient_emails,
                    message.as_string(),
                )

            logger.info(
                f"Successfully sent notification email to {', '.join(self.config.recipient_emails)}"
            )
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(
                "SMTP authentication failed. "
                "For Gmail, use an App Password (not your regular password). "
                "See: https://support.google.com/accounts/answer/185833"
            )
            self._log_performances(performances)
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            self._log_performances(performances)
            return False

    def _log_performances(self, performances: list[Performance]) -> None:
        """Log performances when email can't be sent"""
        logger.info("=" * 60)
        logger.info("PERFORMANCES FOUND (email not sent):")
        logger.info("=" * 60)
        for perf in performances:
            logger.info(f"  {perf.opera_name} @ {perf.opera_house} ({perf.city})")
            logger.info(f"  Date: {perf.date_str or 'TBD'} {perf.time}")
            logger.info(f"  URL: {perf.ticket_url}")
            logger.info("-" * 40)

    def send_startup_notification(self) -> bool:
        """Send a notification that monitoring has started"""
        if not self.config.sender_email or not self.config.sender_password:
            logger.info("Skipping startup notification - email not configured")
            return False

        try:
            subject = "🎭 Opera Ticket Monitor - Uruchomiony"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <h1 style="margin: 0;">🎭 Opera Ticket Monitor</h1>
                    <p style="margin: 8px 0 0 0;">Monitorowanie uruchomione!</p>
                </div>

                <div style="padding: 20px; background: #f9f9f9; border-radius: 8px; margin-top: 16px;">
                    <p>Twój monitor biletów operowych został uruchomiony i szuka:</p>
                    <ul>
                        <li>🎵 <strong>Halka</strong></li>
                        <li>🏰 <strong>Straszny Dwór</strong></li>
                    </ul>
                    <p>Sprawdzanie co 15 minut we wszystkich głównych operach w Polsce.</p>
                    <p>Otrzymasz powiadomienie gdy tylko znajdę dostępne bilety!</p>
                </div>

                <p style="color: #999; font-size: 12px; text-align: center; margin-top: 20px;">
                    Start: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </p>
            </body>
            </html>
            """

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.config.sender_email
            message["To"] = ", ".join(self.config.recipient_emails)
            message.attach(MIMEText(html_body, "html", "utf-8"))

            context = ssl.create_default_context()

            with smtplib.SMTP(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.config.sender_email, self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    self.config.recipient_emails,
                    message.as_string(),
                )

            logger.info("Sent startup notification email")
            return True

        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")
            return False

    def send_error_notification(self, error_message: str) -> bool:
        """Send notification about critical errors"""
        if not self.config.sender_email or not self.config.sender_password:
            return False

        try:
            subject = "⚠️ Opera Ticket Monitor - Błąd"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: #dc3545; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <h1 style="margin: 0;">⚠️ Błąd Monitora</h1>
                </div>

                <div style="padding: 20px; background: #fff3cd; border-radius: 8px; margin-top: 16px; border: 1px solid #ffc107;">
                    <p><strong>Wystąpił błąd:</strong></p>
                    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;">{error_message}</pre>
                </div>

                <p style="color: #999; font-size: 12px; text-align: center; margin-top: 20px;">
                    Czas: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </p>
            </body>
            </html>
            """

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.config.sender_email
            message["To"] = ", ".join(self.config.recipient_emails)
            message.attach(MIMEText(html_body, "html", "utf-8"))

            context = ssl.create_default_context()

            with smtplib.SMTP(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.config.sender_email, self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    self.config.recipient_emails,
                    message.as_string(),
                )

            return True

        except Exception as e:
            logger.error(f"Could not send error notification: {e}")
            return False

    def send_seat_notification(
        self, seat_results: list, min_adjacent: int = 2
    ) -> bool:
        """
        Send notification about performances with adjacent seats available.
        seat_results is a list of SeatCheckResult objects.
        """
        if not seat_results:
            logger.info("No seat results to notify about")
            return True

        if not self.config.sender_email or not self.config.sender_password:
            logger.warning(
                "Email credentials not configured. "
                "Set SENDER_EMAIL and SENDER_PASSWORD environment variables."
            )
            self._log_seat_results(seat_results)
            return False

        try:
            subject = f"🎭 BILETY DOSTĘPNE! {min_adjacent} miejsca obok siebie - Halka/Straszny Dwór"

            # Group by opera
            halka_results = [r for r in seat_results if "Halka" in r.performance.opera_name]
            straszny_results = [r for r in seat_results if "Straszny" in r.performance.opera_name]

            results_html = ""

            if halka_results:
                results_html += "<h2 style='color: #333; margin-top: 20px;'>🎵 Halka</h2>"
                for r in halka_results:
                    results_html += self._create_seat_result_html(r, min_adjacent)

            if straszny_results:
                results_html += "<h2 style='color: #333; margin-top: 20px;'>🏰 Straszny Dwór</h2>"
                for r in straszny_results:
                    results_html += self._create_seat_result_html(r, min_adjacent)

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f5f5f5;">
                <div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 24px; border-radius: 12px 12px 0 0; text-align: center;">
                    <h1 style="margin: 0; font-size: 28px;">🎭 BILETY ZNALEZIONE!</h1>
                    <p style="margin: 12px 0 0 0; font-size: 18px; opacity: 0.95;">
                        {min_adjacent} miejsca obok siebie dostępne!
                    </p>
                </div>

                <div style="background: white; padding: 24px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 12px 12px;">
                    <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                        <p style="margin: 0; color: #155724; font-weight: bold;">
                            ✅ Znaleziono {len(seat_results)} {'spektakl' if len(seat_results) == 1 else 'spektakli'} z {min_adjacent}+ miejscami obok siebie!
                        </p>
                        <p style="margin: 8px 0 0 0; color: #155724; font-size: 14px;">
                            Kup bilety jak najszybciej - mogą szybko zniknąć!
                        </p>
                    </div>

                    {results_html}

                    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">

                    <p style="color: #999; font-size: 12px; text-align: center;">
                        Opera Ticket Monitor - automatyczne powiadomienie<br>
                        {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    </p>
                </div>
            </body>
            </html>
            """

            # Plain text version
            text_body = f"""
🎭 OPERA TICKET MONITOR - BILETY ZNALEZIONE!

Znaleziono {len(seat_results)} spektakli z {min_adjacent}+ miejscami obok siebie!

"""
            for r in seat_results:
                text_body += f"""
{r.performance.opera_name}
{r.performance.opera_house} ({r.performance.city})
Data: {r.performance.date_str or 'Do potwierdzenia'} {r.performance.time}
Miejsca: {', '.join(r.seat_details) if r.seat_details else 'Sprawdź na stronie'}
Link: {r.ticket_url or 'Sprawdź stronę teatru'}
---
"""

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.config.sender_email
            message["To"] = ", ".join(self.config.recipient_emails)

            message.attach(MIMEText(text_body, "plain", "utf-8"))
            message.attach(MIMEText(html_body, "html", "utf-8"))

            context = ssl.create_default_context()

            with smtplib.SMTP(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.config.sender_email, self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    self.config.recipient_emails,
                    message.as_string(),
                )

            logger.info(
                f"Successfully sent seat notification email to {', '.join(self.config.recipient_emails)}"
            )
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(
                "SMTP authentication failed. Use Gmail App Password!"
            )
            self._log_seat_results(seat_results)
            return False
        except Exception as e:
            logger.error(f"Failed to send seat notification email: {e}")
            self._log_seat_results(seat_results)
            return False

    def _create_seat_result_html(self, result, min_adjacent: int) -> str:
        """Create HTML for a single seat check result"""
        perf = result.performance
        date_display = perf.date_str or "Data do potwierdzenia"
        time_display = perf.time or ""

        seats_info = ""
        if result.seat_details:
            seats_info = f"""
            <p style="margin: 8px 0; color: #155724;">
                💺 <strong>{', '.join(result.seat_details[:3])}</strong>
                {f'<br><small>...i więcej</small>' if len(result.seat_details) > 3 else ''}
            </p>
            """

        availability_info = ""
        if result.total_available_seats > 0:
            availability_info = f"""
            <span style="background: #28a745; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                {result.total_available_seats} miejsc dostępnych
            </span>
            """
        elif result.adjacent_seats_count > 0:
            availability_info = f"""
            <span style="background: #28a745; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                {result.adjacent_seats_count}+ par miejsc obok siebie
            </span>
            """

        return f"""
        <div style="border: 2px solid #28a745; border-radius: 12px; padding: 20px; margin: 16px 0; background: #f8fff8;">
            <h3 style="margin: 0 0 12px 0; color: #333; font-size: 20px;">
                🎭 {perf.opera_name}
            </h3>
            <p style="margin: 6px 0; color: #555;">
                🏛️ <strong>{perf.opera_house}</strong> ({perf.city})
            </p>
            <p style="margin: 6px 0; color: #555;">
                📅 {date_display} {time_display}
            </p>
            {seats_info}
            <div style="margin: 12px 0;">
                {availability_info}
            </div>
            <a href="{result.ticket_url}"
               style="display: inline-block; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                      color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px;
                      margin-top: 12px; font-weight: bold; font-size: 16px;">
                🎫 KUP BILETY TERAZ
            </a>
        </div>
        """

    def _log_seat_results(self, seat_results: list) -> None:
        """Log seat results when email can't be sent"""
        logger.info("=" * 60)
        logger.info("SEATS FOUND (email not sent):")
        logger.info("=" * 60)
        for r in seat_results:
            logger.info(f"  🎭 {r.performance.opera_name}")
            logger.info(f"     📍 {r.performance.opera_house} ({r.performance.city})")
            logger.info(f"     📅 {r.performance.date_str or 'TBD'} {r.performance.time}")
            logger.info(f"     💺 Adjacent pairs: {r.adjacent_seats_count}")
            logger.info(f"     🎫 {r.ticket_url}")
            if r.seat_details:
                logger.info(f"     Details: {', '.join(r.seat_details)}")
            logger.info("-" * 40)
