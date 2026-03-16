"""Slack Notifier — Send drift alerts to Slack channels via webhooks."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "critical": "#FF0000",
    "warning": "#FFA500",
    "info": "#36A2EB",
}


class SlackNotifier:
    """Sends drift alert notifications to Slack via incoming webhooks."""

    async def send(
        self,
        webhook_url: str,
        message: dict[str, str],
        severity: str = "warning",
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert to a Slack webhook.

        Parameters
        ----------
        webhook_url : str
            Slack incoming webhook URL.
        message : dict
            Must contain "title" and "body" keys.
        severity : str
            One of: info, warning, critical.
        config : dict, optional
            Additional config: channel, username, mention_users, mention_groups.

        Returns
        -------
        bool indicating success.
        """
        config = config or {}

        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
        mention_text = self._build_mentions(config)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": message["title"][:150],
                },
            },
        ]

        if mention_text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": mention_text},
            })

        body_lines = message["body"].split("\n")
        details_text = "\n".join(body_lines[:20])

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{details_text}```"},
        })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Severity: *{severity.upper()}* | Score: {message.get('score', 'N/A')} | Type: {message.get('drift_type', 'N/A')}",
                },
            ],
        })

        if config.get("dashboard_url"):
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View in DriftGuard"},
                        "url": config["dashboard_url"],
                        "style": "primary",
                    },
                ],
            })

        payload: dict[str, Any] = {
            "blocks": blocks,
            "attachments": [{"color": color, "blocks": []}],
        }

        if config.get("channel"):
            payload["channel"] = config["channel"]
        if config.get("username"):
            payload["username"] = config["username"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)
                if response.status_code == 200:
                    logger.info("Slack alert sent successfully")
                    return True
                else:
                    logger.error("Slack webhook returned status %d: %s", response.status_code, response.text)
                    return False
        except httpx.HTTPError as exc:
            logger.error("Slack notification failed: %s", exc)
            raise

    def _build_mentions(self, config: dict[str, Any]) -> str:
        """Build Slack mention string for users and groups."""
        parts: list[str] = []

        mention_users = config.get("mention_users", [])
        for user in mention_users:
            parts.append(f"<@{user}>")

        mention_groups = config.get("mention_groups", [])
        for group in mention_groups:
            if group == "here":
                parts.append("<!here>")
            elif group == "channel":
                parts.append("<!channel>")
            else:
                parts.append(f"<!subteam^{group}>")

        return " ".join(parts)
