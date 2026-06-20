import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from groq import Groq
from pydantic import BaseModel, Field, ValidationError
from PyPDF2 import PdfReader


PROMPT_INJECTION_PATTERNS = (
    r"ignore all previous instructions",
    r"ignore previous instructions",
    r"system prompt",
    r"developer message",
    r"reveal (?:your|the) prompt",
    r"act as chatgpt",
)

EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?:(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4})"
)


class ResumeAnalysis(BaseModel):
    match_score: int = Field(ge=0, le=100)
    missing_keywords: List[str] = Field(default_factory=list)
    actionable_tips: List[str] = Field(min_length=3, max_length=3)


@dataclass(frozen=True)
class AppConfig:
    groq_api_key: str


class GuardrailViolation(Exception):
    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BadRequestError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def load_config() -> AppConfig:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the environment")
    return AppConfig(groq_api_key=api_key)


def extract_text_from_pdf(file_storage) -> str:
    try:
        reader = PdfReader(BytesIO(file_storage.read()))
    except Exception as exc:  # noqa: BLE001
        raise BadRequestError("Invalid PDF file") from exc

    pages_text: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        if extracted:
            pages_text.append(extracted)

    text = "\n".join(pages_text).strip()
    if not text:
        raise BadRequestError("No extractable text found in the uploaded PDF")
    return text


def sanitize_input_text(text: str) -> str:
    lowered = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            raise GuardrailViolation("Prompt injection detected in resume text")
    return text


def redact_pii(text: str) -> str:
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted


def build_system_prompt() -> str:
    return (
        "You are an AI Resume Analyzer. Return ONLY valid JSON with this exact schema: "
        '{"match_score": number, "missing_keywords": [string], "actionable_tips": [string, string, string]}. '
        "Rules: match_score must be an integer from 0 to 100, missing_keywords must be a list of concise keywords "
        "or phrases absent from the resume, actionable_tips must contain exactly 3 concrete resume improvements. "
        "Do not include markdown, code fences, or extra keys."
    )


def get_job_description() -> str | None:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        job_description = payload.get("job_description")
    else:
        job_description = request.form.get("job_description")

    if isinstance(job_description, str):
        return job_description.strip()
    return None


def analyze_with_groq(resume_text: str, job_description: str, groq_api_key: str) -> ResumeAnalysis:
    client = Groq(api_key=groq_api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "user",
                "content": (
                    "Analyze the resume against the job description and return the JSON object only.\n\n"
                    f"Resume:\n{resume_text}\n\nJob Description:\n{job_description}"
                ),
            },
        ],
    )

    content = response.choices[0].message.content or ""
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BadRequestError("Groq returned invalid JSON") from exc

    try:
        return ResumeAnalysis.model_validate(payload)
    except ValidationError as exc:
        raise BadRequestError("Groq returned JSON that failed validation") from exc


def create_app() -> Flask:
    config = load_config()
    app = Flask(__name__)
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["GROQ_API_KEY"] = config.groq_api_key

    @app.errorhandler(GuardrailViolation)
    def handle_guardrail_violation(error: GuardrailViolation):
        return jsonify({"error": error.message}), error.status_code

    @app.errorhandler(BadRequestError)
    def handle_bad_request(error: BadRequestError):
        return jsonify({"error": error.message}), error.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        return jsonify({"error": "Response validation failed", "details": error.errors()}), 502

    @app.errorhandler(413)
    def handle_payload_too_large(_error):
        return jsonify({"error": "Uploaded file is too large"}), 413

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/analyze", methods=["POST"])
    def analyze():
        resume_file = request.files.get("resume")
        job_description = get_job_description()

        if resume_file is None:
            raise BadRequestError("Missing resume PDF upload under form field 'resume'")
        if not job_description or not isinstance(job_description, str):
            raise BadRequestError("Missing job_description text input")

        resume_text = extract_text_from_pdf(resume_file)
        sanitize_input_text(resume_text)
        sanitized_resume = redact_pii(resume_text)
        sanitized_job_description = redact_pii(job_description)

        result = analyze_with_groq(
            resume_text=sanitized_resume,
            job_description=sanitized_job_description,
            groq_api_key=app.config["GROQ_API_KEY"],
        )
        return jsonify(result.model_dump()), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
