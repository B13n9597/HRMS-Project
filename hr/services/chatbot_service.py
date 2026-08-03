"""
Rule-based HR Chatbot Service.

Uses regex / keyword pattern matching to respond to common HR queries.
No external AI API dependencies — runs entirely in-process.
"""

import re
from typing import Optional


class HRChatbotService:
    """
    Lightweight, rule-based HR assistant that matches user messages
    against predefined intent patterns and returns helpful responses.
    """

    def __init__(self, user=None):
        self.user = user
        self._user_name = self._resolve_name()

    # ── private helpers ──────────────────────────────────────────────
    def _resolve_name(self) -> str:
        if self.user and hasattr(self.user, 'get_full_name'):
            name = self.user.get_full_name()
            if name and name.strip():
                return name.strip()
            return getattr(self.user, 'username', 'there')
        return 'there'

    # ── intent patterns ──────────────────────────────────────────────
    # Each entry: (compiled regex, response string or callable)
    _INTENTS = None

    def _build_intents(self):
        """Lazy-build intent list so we can interpolate user name."""
        name = self._user_name
        self._INTENTS = [
            # ── Greetings ────────────────────────────────────────────
            (
                re.compile(
                    r'\b(hi|hello|hey|good\s*morning|good\s*afternoon|good\s*evening'
                    r'|howdy|hola|greetings|sup|what\'?s\s*up)\b',
                    re.IGNORECASE,
                ),
                f"👋 Hello, {name}! I'm the ACT HR Assistant. "
                f"How can I help you today?\n\n"
                f"I can answer questions about:\n"
                f"• Working hours & schedules\n"
                f"• Leave policies & balances\n"
                f"• QR code attendance check-in\n"
                f"• Payroll & salary slips\n"
                f"• HR support & contacts",
            ),
            # ── Working Hours / Schedules ────────────────────────────
            (
                re.compile(
                    r'\b(work(ing)?\s*hours?|schedule|shift|office\s*hours?'
                    r'|office\s*time|when\s*(do|does|should)\s*(i|we)\s*(start|come|arrive|report)'
                    r'|start\s*time|end\s*time|closing\s*time'
                    r'|what\s*time\s*(do|does)\s*(the\s*)?(office|work))\b',
                    re.IGNORECASE,
                ),
                "🕐 **Working Hours**\n\n"
                "• **Standard hours:** Monday – Friday, 8:00 AM – 5:00 PM\n"
                "• **Lunch break:** 12:00 PM – 1:00 PM\n"
                "• **Late arrival threshold:** After 9:00 AM is flagged as late\n"
                "• **Weekends & public holidays:** Office closed\n\n"
                "For shift-specific schedules, please contact your department supervisor "
                "or check the HR portal.",
            ),
            # ── Leave Policies ───────────────────────────────────────
            (
                re.compile(
                    r'\b(leave|annual\s*leave|sick\s*leave|maternity|paternity'
                    r'|vacation|time\s*off|pto|day\s*off|days?\s*off'
                    r'|leave\s*(balance|policy|policies|request|apply|application|entitlement)'
                    r'|how\s*(many|much)\s*(leave|days?)\s*(do|does|can))\b',
                    re.IGNORECASE,
                ),
                "📋 **Leave Policies**\n\n"
                "• **Annual Leave:** 21 working days per year\n"
                "• **Sick Leave:** 14 days (medical certificate required after 2 consecutive days)\n"
                "• **Maternity Leave:** 90 calendar days\n"
                "• **Paternity Leave:** 14 calendar days\n"
                "• **Compassionate Leave:** Up to 5 days\n"
                "• **Study Leave:** Subject to approval\n\n"
                "**To request leave:**\n"
                "1. Go to **My Leave** in the sidebar\n"
                "2. Click **Request Leave**\n"
                "3. Select leave type, dates, and submit\n\n"
                "Your current leave balance is visible in the Leave Manager page.",
            ),
            # ── QR Code Attendance ───────────────────────────────────
            (
                re.compile(
                    r'\b(qr\s*code|check[\s-]?in|clock[\s-]?in|clock[\s-]?out'
                    r'|attendance\s*(check|mark|record|system|scan|qr|how)'
                    r'|scan\s*(my\s*)?(qr|code|badge)'
                    r'|how\s*(do|to)\s*(i\s*)?(check|clock|mark)\s*(in|out|attendance))\b',
                    re.IGNORECASE,
                ),
                "📱 **QR Code Attendance Check-In**\n\n"
                "ACT HRMS uses dynamic QR codes for secure attendance tracking.\n\n"
                "**How to check in:**\n"
                "1. Open the **My QR Code** page from the sidebar\n"
                "2. Show your personal QR code to the kiosk/tablet scanner\n"
                "3. The system automatically records your **time in** and **time out**\n\n"
                "**Key features:**\n"
                "• QR codes are unique and time-sensitive for security\n"
                "• Digital signature verification is also supported\n"
                "• You can view your attendance history under **My Attendance**\n\n"
                "Having trouble scanning? Contact HR or use the **Manual Attendance** option.",
            ),
            # ── Payroll / Salary Slips ───────────────────────────────
            (
                re.compile(
                    r'\b(payroll|salary|pay\s*slip|payslip|pay\s*stub|wage|compensation'
                    r'|pay\s*day|when\s*(do|will)\s*(i|we)\s*(get\s*)?paid'
                    r'|salary\s*(slip|statement|details|breakdown)'
                    r'|deduction|tax|net\s*pay|gross\s*pay)\b',
                    re.IGNORECASE,
                ),
                "💰 **Payroll & Salary Information**\n\n"
                "• **Pay cycle:** Monthly (last working day of each month)\n"
                "• **Salary slips:** Available under **My Salary Slips** in the sidebar\n"
                "• **Deductions:** Tax, pension, and other statutory deductions are itemized\n\n"
                "**To view your salary slips:**\n"
                "1. Go to **My Salary Slips** in the navigation menu\n"
                "2. Select the month/year to download your payslip\n\n"
                "For payroll queries or discrepancies, please contact the Finance department "
                "or raise a ticket through HR Support.",
            ),
            # ── HR Support / Contact ─────────────────────────────────
            (
                re.compile(
                    r'\b(hr\s*(support|contact|help|team|department|office|email|phone|number)'
                    r'|contact\s*hr|reach\s*hr|talk\s*to\s*hr'
                    r'|help\s*desk|support\s*(team|desk|contact|number)'
                    r'|grievance|complaint|issue|problem|report\s*(a\s*)?problem'
                    r'|who\s*(do|should|can)\s*i\s*(contact|call|email|reach|talk))\b',
                    re.IGNORECASE,
                ),
                "📞 **HR Support & Contacts**\n\n"
                "• **HR Department Email:** hr@act.ac.tz\n"
                "• **HR Office:** Administration Building, Ground Floor\n"
                "• **Office Hours:** Mon–Fri, 8:00 AM – 5:00 PM\n\n"
                "**For specific issues:**\n"
                "• **Leave/Attendance:** Use the leave & attendance modules in the portal\n"
                "• **Payroll queries:** Contact the Finance department\n"
                "• **Grievances:** Submit via **My Grievances** in the sidebar\n"
                "• **Training requests:** Submit via **My Training** page\n\n"
                "We aim to respond to all queries within 24 working hours.",
            ),
            # ── Thank you ───────────────────────────────────────────
            (
                re.compile(
                    r'\b(thank\s*(you|u)|thanks|thx|appreciate|cheers)\b',
                    re.IGNORECASE,
                ),
                f"😊 You're welcome, {name}! Don't hesitate to ask if you need anything else.",
            ),
            # ── Goodbye ─────────────────────────────────────────────
            (
                re.compile(
                    r'\b(bye|goodbye|good\s*bye|see\s*you|later|good\s*night|take\s*care)\b',
                    re.IGNORECASE,
                ),
                f"👋 Goodbye, {name}! Have a great day. I'm here whenever you need HR assistance.",
            ),
        ]

    # ── public API ───────────────────────────────────────────────────
    def get_response(self, message: str) -> str:
        """
        Match the user's message against known intents and return
        an appropriate response string.  Falls back to a helpful
        default if no intent is matched.
        """
        if self._INTENTS is None:
            self._build_intents()

        if not message or not message.strip():
            return self._fallback()

        text = message.strip()

        for pattern, response in self._INTENTS:
            if pattern.search(text):
                return response

        return self._fallback()

    def _fallback(self) -> str:
        return (
            f"🤔 I'm not sure I understood that, {self._user_name}. "
            f"I'm a rule-based assistant and can help with these topics:\n\n"
            f"• **Working hours** — \"What are the office hours?\"\n"
            f"• **Leave policies** — \"How many leave days do I have?\"\n"
            f"• **QR attendance** — \"How do I check in?\"\n"
            f"• **Payroll** — \"When do I get paid?\"\n"
            f"• **HR contacts** — \"How do I reach HR?\"\n\n"
            f"Try asking about one of these topics!"
        )
