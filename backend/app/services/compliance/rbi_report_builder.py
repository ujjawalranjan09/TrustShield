"""RBI compliance report builder.

Generates quarterly fraud analytics PDF reports for RBI compliance
using ReportLab. Uses hardcoded mock data — replace with real database
queries in production.
"""

import io
import logging
from typing import Any, Dict

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


class RBIReportBuilder:
    """Generate RBI quarterly fraud analytics reports as PDF."""

    def generate_quarterly_report(self, client_id: str, quarter: str) -> bytes:
        """Generate a quarterly compliance report.

        Args:
            client_id: The client identifier (e.g. bank name).
            quarter: Quarter identifier (e.g. 'Q3_2026').

        Returns:
            Raw PDF bytes.
        """
        stats: Dict[str, Any] = {
            "total_scans": 1450230,
            "fraud_incidents": 12045,
            "entities_blacklisted": 890,
            "false_positive_rate": "1.2%",
            "intervention_effectiveness": "94.5%",
            "top_scammers": ["abc@okhdfcbank", "987654****", "876543****"],
        }

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, "TrustShield - RBI Quarterly Fraud Analytics Report")
        c.setFont("Helvetica", 12)
        c.drawString(50, 730, f"Client ID: {client_id} | Quarter: {quarter}")

        # Section 1: Overview
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 680, "1. Overall Metrics")
        c.setFont("Helvetica", 12)
        c.drawString(70, 650, f"Total Transaction Scans: {stats['total_scans']}")
        c.drawString(
            70, 630, f"Total Fraud Incidents Detected: {stats['fraud_incidents']}"
        )
        c.drawString(70, 610, f"Entities Blacklisted: {stats['entities_blacklisted']}")
        c.drawString(70, 590, f"False Positive Rate: {stats['false_positive_rate']}")
        c.drawString(
            70,
            570,
            f"Intervention Effectiveness: {stats['intervention_effectiveness']}",
        )

        # Section 2: Entities
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 520, "2. Top Flagged Entities (Masked)")
        c.setFont("Helvetica", 12)
        y = 490
        for idx, entity in enumerate(stats["top_scammers"]):
            c.drawString(70, y, f"{idx + 1}. {entity}")
            y -= 20

        # Section 3: Compliance Mapping
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y - 30, "3. RBI Compliance Mapping")
        c.setFont("Helvetica", 10)
        c.drawString(
            70,
            y - 60,
            "Mandate: Real-time fraud detection capability. Status: Met (<300ms latency).",
        )
        c.drawString(
            70,
            y - 80,
            "Mandate: Immutable audit trails. Status: Met (All decisions logged to ELK/PostgreSQL).",
        )
        c.drawString(
            70,
            y - 100,
            "Mandate: Entity blacklisting and reporting. Status: Met (1930 Helpline integration).",
        )

        c.showPage()
        c.save()

        buffer.seek(0)
        logger.info(
            "Generated RBI report for client=%s quarter=%s (%d bytes)",
            client_id,
            quarter,
            buffer.tell(),
        )
        return buffer.getvalue()


if __name__ == "__main__":
    builder = RBIReportBuilder()
    pdf_bytes = builder.generate_quarterly_report("HDFC_PROD", "Q3_2026")
    with open("rbi_report_mock.pdf", "wb") as f:
        f.write(pdf_bytes)
    logger.info("PDF generated successfully.")
