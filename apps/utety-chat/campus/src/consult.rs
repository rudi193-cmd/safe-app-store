//! Python sidecar bridge for Consultation Chamber LLM turns.

use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsultHistoryTurn {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize)]
struct ConsultRequest<'a> {
    professor: &'a str,
    message: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    course_code: Option<&'a str>,
    history: &'a [ConsultHistoryTurn],
    compact: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ConsultResponse {
    pub ok: bool,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub provider: String,
    #[serde(default)]
    pub tier: String,
    #[serde(default)]
    pub error: String,
}

fn sidecar_script() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("campus_consult.py")
}

fn python_bin() -> String {
    std::env::var("UTETY_PYTHON").unwrap_or_else(|_| "python3".into())
}

fn timeout() -> Duration {
    let secs = std::env::var("UTETY_CONSULT_TIMEOUT_SECS")
        .ok()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(60);
    Duration::from_secs(secs)
}

pub fn run_consult(
    professor: &str,
    message: &str,
    course_code: Option<&str>,
    history: &[ConsultHistoryTurn],
) -> color_eyre::Result<ConsultResponse> {
    let script = sidecar_script();
    if !script.is_file() {
        return Ok(ConsultResponse {
            ok: false,
            error: format!("sidecar missing: {}", script.display()),
            ..Default::default()
        });
    }

    let req = ConsultRequest {
        professor,
        message,
        course_code,
        history,
        compact: true,
    };
    let payload = serde_json::to_string(&req)?;

    let mut child = Command::new(python_bin())
        .arg(&script)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| color_eyre::eyre::eyre!("spawn campus_consult.py: {e}"))?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(payload.as_bytes())?;
    }

    let limit = timeout();
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= limit {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(ConsultResponse {
                ok: false,
                error: format!("consultation timed out after {}s", limit.as_secs()),
                ..Default::default()
            });
        }
        thread::sleep(Duration::from_millis(50));
    };

    let mut stdout = String::new();
    if let Some(mut pipe) = child.stdout.take() {
        let _ = pipe.read_to_string(&mut stdout);
    }
    let mut stderr = String::new();
    if let Some(mut pipe) = child.stderr.take() {
        let _ = pipe.read_to_string(&mut stderr);
    }

    let parsed: ConsultResponse = serde_json::from_str(stdout.trim()).unwrap_or(ConsultResponse {
        ok: false,
        error: if stdout.trim().is_empty() {
            format!(
                "sidecar failed (exit {}): {}",
                status.code().unwrap_or(-1),
                stderr.trim()
            )
        } else {
            format!("invalid sidecar json: {}", stdout.trim())
        },
        ..Default::default()
    });
    Ok(parsed)
}

impl Default for ConsultResponse {
    fn default() -> Self {
        Self {
            ok: false,
            text: String::new(),
            provider: String::new(),
            tier: String::new(),
            error: String::new(),
        }
    }
}
