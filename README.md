# Enterprise AI Resume Checker & LLM Guardrail Gateway

A hardened, full-stack microservice architecture built to securely map candidate qualifications against enterprise job requirements. The system is engineered around a robust **LLM Guardrail Gateway** pattern, providing advanced protection against data leakage, malicious inputs, and structural hallucinations while leveraging the edge-inference performance of the Groq (Llama 3) API.

---

## 🏗️ Architectural Pattern: The LLM Guardrail Gateway

In an enterprise context, exposing large language models to user-generated documents (like PDFs) without interception is a critical security and operational risk.

This application is engineered using the **LLM Guardrail Gateway** pattern. The backend acts as a strict proxy, intercepting and validating all communication between the untrusted client-side UI and the trusted external LLM API.

```text
                                [ CLIENT ZONE ]
 [ Browser UI ] ────────────────( Multipart FormData POST )───────────────┐
                                                                          │
                                [ ENTERPRISE ZONE ]                       │
                                                                          ▼
 ┌───[ Vercel Serverless Function ]──────────────────────────────────[ /analyze Endpoint ]───┐
 │                                                                                            │
 │   >> STEP 1: Input Pre-Processing (Text Extraction & Structuring)                          │
 │                                                                                            │
 │   🔒[ GUARDRAIL 1: INJECTION SCANNER ]────────────────────────────────────────────────────┤
 │   >> Regex and heuristic analysis to block 'ignore previous instruction' attacks            │
 │   >> or other adversarial prompt manipulation in the Job Description.                      │
 │                                                                                            │
 │   🛡️[ GUARDRAIL 2: PII REDACTOR (Data Leakage Prevention) ]───────────────────────────────┤
 │   >> Strips all Emails and Phone Numbers from the extracted Resume PDF text                 │
 │   >> before transmission, ensuring candidate privacy is preserved (GDPR/CCPA compliance). │
 │                                                                                            │
 │   >> STEP 2: Edge Inference Call                                                           │
 │   ────────────────────────────────────( Groq SDK / Llama 3 )───────────────────────────> │
 │                                                                                            │
 │   >> STEP 3: Output Post-Processing                                                        │
 │                                                                                            │
 │   ✅[ GUARDRAIL 3: DETERMINISTIC SCHEMA VALIDATION ]──────────────────────────────────────┤
 │   >> Uses Pydantic to strictly enforce the JSON structure returned by the LLM.             │
 │   >> Prevents hallucinations, model changes, or incomplete JSON from breaking the UI.      │
 │                                                                                            │
 └───( Structured JSON Response / 200 )───────────────────────────────────────────────────┘

```

---

## 🧠 Core Engineering Features

### 1. LLM Security Implementation

* **Prompt Injection Blocking (Guardrail 1):** Proactively scans the user-submitted Job Description and Resume text for adversarial substrings designed to override the system instructions. Malicious requests are terminated with a `403 Forbidden` status.
* **Data Leakage Prevention (Guardrail 2):** To comply with internal data governance policies, all Personally Identifiable Information (PII)—specifically email addresses and US/International phone numbers—is redacted from the resume text using Regex before the payload reaches the Groq API.
* **JSON-Mode Integrity (Guardrail 3):** Combines the Groq API's native JSON mode with a strict `Pydantic` `BaseModel`. This ensures that even if the underlying model changes its response pattern, the output structure remains deterministic (`int` scores remain integers, missing keywords remain arrays), preventing front-end parsing failures.

### 2. High-Performance Inference Engine

* **Sub-Second Processing:** Utilizes the flagship **Llama-3.3-70b-versatile** model via the **Groq LPU (Language Processing Unit)** architecture. By shifting the complex mathematical mapping and tokenization tasks from the backend function to Groq’s edge-inference system, the application achieves a near-instantaneous structured evaluation of even dense documents.
* **Optimized Vercel Deployment:** The Flask microservice is containerized and deployed as a Vercel Serverless Function, ensuring automatic scaling and instant response times without cold starts by running the Python worker on the Vercel Edge Network.

### 3. Decoupled Microservice Design

* **Stateless REST API:** The backend serves as a stateless `/analyze` REST endpoint. It can be easily re-integrated into existing HRIS (Human Resource Information Systems) or corporate Applicant Tracking Systems (ATS).
* **Minimalist Frontend:** The UI uses vanilla JavaScript `fetch` calls, making it completely decoupled from the specific backend implementation.

---

## 💻 Technical Implementation Details

### API Specification

**Endpoint:** `POST /analyze`
**Content-Type:** `multipart/form-data`

**Request Parameters:**

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `resume` | `File (PDF)` | Yes | The candidate's resume document. Only PDF format is parsed. |
| `job_description` | `String` | Yes | The full text of the role requirements. |

**Success Response (JSON):**

```json
{
  "match_score": 75,
  "missing_keywords": [
    "AWS Lambda",
    "Docker",
    "SQL Performance Tuning"
  ],
  "actionable_improvements": [
    "Increase emphasis on specific cloud infrastructure deployment scenarios.",
    "Detail quantifiable metrics for past project successes (e.g., 'optimized latency by 30%')."
  ]
}

```

### Local Setup & Development

1. **Clone the Repository:**
```bash

```



git clone https://github.com/AnberAziz5/ai-resume-checker.git
cd ai-resume-checker

```

2.  **Initialize Environment:**
    Create a `.env` file and add your secure credentials:
    ```env
GROQ_API_KEY=gsk_your_secure_groq_key_here

```

3. **Install Dependencies:**
```bash

```



pip install -r requirements.txt

```

4.  **Run the Backend Microservice:**
    ```bash
flask run --port=5000

```

### Production Deployment

The application is configured for a single-click, full-stack deployment on the **Vercel** platform, managing both the static frontend assets and the serverless Python functions from the `vercel.json` configuration. Ensure the `GROQ_API_KEY` is added to the Vercel project environment variables.