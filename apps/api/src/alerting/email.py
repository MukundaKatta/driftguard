"""Email Notifier — Send drift alerts via AWS SES."""

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends drift alert emails via AWS SES."""

    def __init__(self, region_name: str = "us-east-1", sender: str = "alerts@driftguard.io"):
        self.region_name = region_name
        self.sender = sender

    async def send(
        self,
        to_address: str,
        message: dict[str, str],
        severity: str = "warning",
        drift_result: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert email via SES.

        Parameters
        ----------
        to_address : str
            Recipient email address.
        message : dict
            Must contain "title" and "body".
        severity : str
            Alert severity level.
        drift_result : dict, optional
            Full drift result for email body enrichment.
        config : dict, optional
            Additional config: cc, sender_override, reply_to.

        Returns
        -------
        bool indicating success.
        """
        config = config or {}
        drift_result = drift_result or {}

        sender = config.get("sender_override", self.sender)
        subject = message["title"][:998]  # SES subject limit

        html_body = self._build_html(message, severity, drift_result, config)
        text_body = message["body"]

        destination: dict[str, Any] = {"ToAddresses": [to_address]}
        cc = config.get("cc", [])
        if cc:
            destination["CcAddresses"] = cc if isinstance(cc, list) else [cc]

        try:
            ses = boto3.client("ses", region_name=self.region_name)
            response = ses.send_email(
                Source=sender,
                Destination=destination,
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                },
                ReplyToAddresses=config.get("reply_to", [sender]),
            )
            message_id = response.get("MessageId")
            logger.info("Email alert sent: to=%s, message_id=%s", to_address, message_id)
            return True
        except ClientError as exc:
            logger.error("SES email send failed: %s", exc)
            raise

    def _build_html(
        self,
        message: dict[str, str],
        severity: str,
        drift_result: dict[str, Any],
        config: dict[str, Any],
    ) -> str:
        """Build an HTML email body for the drift alert."""
        severity_colors = {
            "critical": "#DC2626",
            "warning": "#F59E0B",
            "info": "#3B82F6",
        }
        color = severity_colors.get(severity, "#6B7280")

        drift_type = drift_result.get("drift_type", message.get("drift_type", "N/A"))
        score = drift_result.get("score", message.get("score", "N/A"))
        details = drift_result.get("details", {})

        detail_rows = ""
        for key, value in details.items():
            if not isinstance(value, (list, dict)):
                detail_rows += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #E5E7EB; color: #6B7280; font-size: 14px;">{key}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #E5E7EB; color: #111827; font-size: 14px;">{value}</td>
                </tr>"""

        dashboard_url = config.get("dashboard_url", "")
        button_html = ""
        if dashboard_url:
            button_html = f"""
            <div style="text-align: center; margin-top: 24px;">
                <a href="{dashboard_url}" style="display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: #FFFFFF; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">
                    View in DriftGuard
                </a>
            </div>"""

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #F3F4F6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div style="background-color: {color}; padding: 20px 24px;">
                <h1 style="margin: 0; color: #FFFFFF; font-size: 18px; font-weight: 600;">
                    {message['title']}
                </h1>
            </div>
            <div style="padding: 24px;">
                <div style="display: flex; gap: 16px; margin-bottom: 20px;">
                    <div style="background-color: #F9FAFB; border-radius: 6px; padding: 12px 16px; flex: 1;">
                        <div style="font-size: 12px; color: #6B7280; text-transform: uppercase;">Drift Type</div>
                        <div style="font-size: 16px; font-weight: 600; color: #111827; margin-top: 4px;">{drift_type}</div>
                    </div>
                    <div style="background-color: #F9FAFB; border-radius: 6px; padding: 12px 16px; flex: 1;">
                        <div style="font-size: 12px; color: #6B7280; text-transform: uppercase;">Score</div>
                        <div style="font-size: 16px; font-weight: 600; color: #111827; margin-top: 4px;">{score}</div>
                    </div>
                    <div style="background-color: #F9FAFB; border-radius: 6px; padding: 12px 16px; flex: 1;">
                        <div style="font-size: 12px; color: #6B7280; text-transform: uppercase;">Severity</div>
                        <div style="font-size: 16px; font-weight: 600; color: {color}; margin-top: 4px;">{severity.upper()}</div>
                    </div>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin-top: 16px;">
                    <thead>
                        <tr>
                            <th style="padding: 8px 12px; text-align: left; background-color: #F9FAFB; font-size: 12px; color: #6B7280; text-transform: uppercase;">Metric</th>
                            <th style="padding: 8px 12px; text-align: left; background-color: #F9FAFB; font-size: 12px; color: #6B7280; text-transform: uppercase;">Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        {detail_rows}
                    </tbody>
                </table>
                {button_html}
            </div>
            <div style="padding: 16px 24px; background-color: #F9FAFB; border-top: 1px solid #E5E7EB;">
                <p style="margin: 0; font-size: 12px; color: #9CA3AF; text-align: center;">
                    Sent by DriftGuard ML Monitoring Platform
                </p>
            </div>
        </div>
    </div>
</body>
</html>"""
