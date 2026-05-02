use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fmt;

#[derive(Clone, Debug)]
pub struct ReflectClient {
    base_url: String,
    api_key: String,
    client: reqwest::Client,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectJob {
    pub job_id: String,
    pub status: String,
    pub progress_pct: f64,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedFact {
    pub key: String,
    pub value: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionJobSummary {
    pub id: String,
    pub agent_id: String,
    pub status: String,
    pub job_type: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub memories_processed: i64,
    pub memories_updated: i64,
    pub memories_archived: i64,
    pub error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionResult {
    pub id: String,
    pub job_id: String,
    pub memory_id: String,
    pub result_type: String,
    pub output: Value,
    pub confidence: f64,
    pub applied: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionJobDetails {
    pub job: ReflectionJobSummary,
    pub results: Vec<ReflectionResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Preference {
    pub id: String,
    pub agent_id: String,
    pub category: String,
    pub key: String,
    pub value: Value,
    pub confidence: f64,
    pub confirmation_count: i64,
    pub is_active: bool,
    pub first_seen_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contradiction {
    pub id: String,
    pub agent_id: String,
    pub memory_id_a: String,
    pub memory_id_b: String,
    pub field: String,
    pub value_a: Value,
    pub value_b: Value,
    pub detected_at: String,
    pub resolved: bool,
}

#[derive(Debug)]
pub enum ReflectError {
    Http(reqwest::Error),
    Json(serde_json::Error),
    ApiStatus { status: StatusCode, body: String },
    InvalidBaseUrl(String),
}

impl fmt::Display for ReflectError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(err) => write!(f, "http error: {err}"),
            Self::Json(err) => write!(f, "json error: {err}"),
            Self::ApiStatus { status, body } => write!(f, "api returned {status}: {body}"),
            Self::InvalidBaseUrl(url) => write!(f, "invalid base_url: {url}"),
        }
    }
}

impl std::error::Error for ReflectError {}

impl From<reqwest::Error> for ReflectError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

impl From<serde_json::Error> for ReflectError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

#[derive(Debug, Serialize)]
struct TriggerRequest {
    agent_id: String,
    job_type: String,
    options: Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct TriggerDryRunResponse {
    processed: Option<i64>,
    updated: Option<i64>,
    archived: Option<i64>,
    promoted: Option<i64>,
    contradictions: Option<i64>,
    duplicates: Option<i64>,
    preferences: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct ProfileResponse {
    facts: BTreeMap<String, Value>,
}

#[derive(Debug, Deserialize)]
struct PreferencesResponse {
    preferences: Vec<Preference>,
}

#[derive(Debug, Serialize)]
struct ResolveContradictionRequest {
    contradiction_id: String,
    strategy: String,
    merged_value: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct ErrorDetail {
    message: Option<String>,
}

impl ReflectClient {
    pub fn new(
        base_url: impl Into<String>,
        api_key: impl Into<String>,
    ) -> Result<Self, ReflectError> {
        let base_url = base_url.into().trim_end_matches('/').to_string();
        if base_url.is_empty()
            || !(base_url.starts_with("http://") || base_url.starts_with("https://"))
        {
            return Err(ReflectError::InvalidBaseUrl(base_url));
        }

        Ok(Self {
            base_url,
            api_key: api_key.into(),
            client: reqwest::Client::new(),
        })
    }

    async fn into_api_error(response: reqwest::Response) -> ReflectError {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();

        if let Ok(parsed) = serde_json::from_str::<ErrorDetail>(&body) {
            if let Some(message) = parsed.message {
                return ReflectError::ApiStatus {
                    status,
                    body: message,
                };
            }
        }

        ReflectError::ApiStatus { status, body }
    }

    pub async fn trigger_job(
        &self,
        job_type: &str,
        workspace_id: &str,
        dry_run: bool,
    ) -> Result<ReflectJob, ReflectError> {
        let request = TriggerRequest {
            agent_id: workspace_id.to_string(),
            job_type: job_type.to_string(),
            options: serde_json::json!({}),
        };

        if dry_run {
            let url = format!("{}/api/v1/reflect/trigger/dry-run", self.base_url);
            let response = self
                .client
                .post(url)
                .header("X-Claw-Api-Key", &self.api_key)
                .json(&request)
                .send()
                .await?;

            if !response.status().is_success() {
                return Err(Self::into_api_error(response).await);
            }

            let preview: TriggerDryRunResponse = response.json().await?;
            let message = serde_json::to_string(&preview)?;
            return Ok(ReflectJob {
                job_id: "dry-run".to_string(),
                status: "preview".to_string(),
                progress_pct: 0.0,
                message,
            });
        }

        let url = format!("{}/api/v1/reflect/trigger", self.base_url);
        let response = self
            .client
            .post(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        Ok(response.json::<ReflectJob>().await?)
    }

    pub async fn get_facts(&self, workspace_id: &str) -> Result<Vec<ExtractedFact>, ReflectError> {
        let url = format!("{}/api/v1/profiles/{}", self.base_url, workspace_id);
        let response = self
            .client
            .get(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        let profile: ProfileResponse = response.json().await?;
        Ok(profile
            .facts
            .into_iter()
            .map(|(key, value)| ExtractedFact { key, value })
            .collect())
    }

    pub async fn list_jobs(
        &self,
        agent_id: Option<&str>,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Vec<ReflectionJobSummary>, ReflectError> {
        let url = format!("{}/api/v1/jobs", self.base_url);
        let mut query: Vec<(String, String)> = Vec::new();
        if let Some(id) = agent_id {
            query.push(("agent_id".to_string(), id.to_string()));
        }
        if let Some(state) = status {
            query.push(("status".to_string(), state.to_string()));
        }
        if let Some(value) = limit {
            query.push(("limit".to_string(), value.to_string()));
        }
        if let Some(value) = offset {
            query.push(("offset".to_string(), value.to_string()));
        }

        let response = self
            .client
            .get(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .query(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        Ok(response.json::<Vec<ReflectionJobSummary>>().await?)
    }

    pub async fn get_job(&self, job_id: &str) -> Result<ReflectionJobDetails, ReflectError> {
        let url = format!("{}/api/v1/jobs/{}", self.base_url, job_id);
        let response = self
            .client
            .get(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        Ok(response.json::<ReflectionJobDetails>().await?)
    }

    pub async fn get_preferences(
        &self,
        workspace_id: &str,
    ) -> Result<Vec<Preference>, ReflectError> {
        let url = format!(
            "{}/api/v1/profiles/{}/preferences",
            self.base_url, workspace_id
        );
        let response = self
            .client
            .get(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        let body: PreferencesResponse = response.json().await?;
        Ok(body.preferences)
    }

    pub async fn get_contradictions(
        &self,
        workspace_id: &str,
    ) -> Result<Vec<Contradiction>, ReflectError> {
        let url = format!(
            "{}/api/v1/profiles/{}/contradictions",
            self.base_url, workspace_id
        );
        let response = self
            .client
            .get(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        Ok(response.json::<Vec<Contradiction>>().await?)
    }

    pub async fn resolve_contradiction(
        &self,
        workspace_id: &str,
        contradiction_id: &str,
        strategy: &str,
        merged_value: Option<Value>,
    ) -> Result<Contradiction, ReflectError> {
        let request = ResolveContradictionRequest {
            contradiction_id: contradiction_id.to_string(),
            strategy: strategy.to_string(),
            merged_value,
        };

        let url = format!(
            "{}/api/v1/profiles/{}/contradictions/{}/resolve",
            self.base_url, workspace_id, contradiction_id
        );
        let response = self
            .client
            .post(url)
            .header("X-Claw-Api-Key", &self.api_key)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(Self::into_api_error(response).await);
        }

        Ok(response.json::<Contradiction>().await?)
    }
}
