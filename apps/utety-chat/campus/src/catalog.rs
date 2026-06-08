//! UTETY campus catalog types and loader.

use serde::Deserialize;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Deserialize)]
pub struct Catalog {
    pub meta: Meta,
    pub admissions: Vec<AdmissionSection>,
    pub dept_tabs: Vec<DeptTab>,
    pub faculty: Vec<Faculty>,
    pub courses: Vec<Course>,
    pub research: Vec<PaperCard>,
    pub dispatches: Vec<PaperCard>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Meta {
    pub title: String,
    pub est: u32,
    pub tagline: String,
    pub subtitle: String,
    pub mottos: Vec<String>,
    pub stats: Vec<Stat>,
    pub about: String,
    pub gerald_quote: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Stat {
    pub value: String,
    pub label: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AdmissionSection {
    pub title: String,
    pub body: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DeptTab {
    pub label: String,
    pub keys: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Faculty {
    pub name: String,
    pub portrait: String,
    pub bio: String,
    pub dept: String,
    pub location: String,
    pub course: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Course {
    pub code: String,
    pub dept_key: String,
    pub dept_full: String,
    pub title: String,
    pub instructor: String,
    pub credits: String,
    pub prereq: String,
    pub cross: Option<String>,
    pub desc: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PaperCard {
    pub label: String,
    pub title: String,
    pub summary: String,
    pub meta: String,
    pub file: String,
    pub modal_label: String,
    pub kind: String,
}

pub fn campus_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

pub fn catalog_path() -> PathBuf {
    campus_dir().join("catalog/catalog.json")
}

pub fn papers_dir() -> PathBuf {
    campus_dir().join("../web/papers")
}

pub fn load_catalog() -> color_eyre::Result<Catalog> {
    let path = catalog_path();
    let raw = fs::read_to_string(&path)
        .map_err(|e| color_eyre::eyre::eyre!("read {}: {e}", path.display()))?;
    Ok(serde_json::from_str(&raw)?)
}

pub fn load_paper(file: &str) -> color_eyre::Result<String> {
    let path = papers_dir().join(file);
    fs::read_to_string(&path).map_err(|e| color_eyre::eyre::eyre!("read {}: {e}", path.display()))
}

pub fn markdown_to_lines(md: &str, width: usize) -> Vec<String> {
    use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd};

    let mut lines: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut in_code = false;

    let push_line = |lines: &mut Vec<String>, current: &mut String| {
        let t = current.trim_end().to_string();
        if !t.is_empty() {
            for wrapped in wrap_text(&t, width) {
                lines.push(wrapped);
            }
        }
        current.clear();
    };

    for event in Parser::new_ext(md, Options::empty()) {
        match event {
            Event::Start(Tag::CodeBlock(_)) => {
                push_line(&mut lines, &mut current);
                in_code = true;
            }
            Event::End(TagEnd::CodeBlock) => {
                push_line(&mut lines, &mut current);
                in_code = false;
            }
            Event::Start(Tag::Heading { .. }) => {
                push_line(&mut lines, &mut current);
            }
            Event::End(TagEnd::Heading(_)) => {
                push_line(&mut lines, &mut current);
                if let Some(last) = lines.last_mut() {
                    *last = format!("▸ {}", last.trim_start());
                }
            }
            Event::Start(Tag::Paragraph) => {
                push_line(&mut lines, &mut current);
            }
            Event::End(TagEnd::Paragraph) => {
                push_line(&mut lines, &mut current);
            }
            Event::SoftBreak | Event::HardBreak => {
                current.push(' ');
            }
            Event::Text(t) | Event::Code(t) => {
                current.push_str(&t);
            }
            Event::Rule => {
                push_line(&mut lines, &mut current);
                lines.push("─".repeat(width.min(40)));
            }
            _ => {}
        }
    }
    push_line(&mut lines, &mut current);
    if in_code {
        push_line(&mut lines, &mut current);
    }
    if lines.is_empty() {
        lines.push("(empty document)".into());
    }
    lines
}

fn wrap_text(text: &str, width: usize) -> Vec<String> {
    let w = width.max(20);
    let mut out = Vec::new();
    let mut line = String::new();
    let mut col = 0usize;

    for word in text.split_whitespace() {
        let word_w = unicode_width::UnicodeWidthStr::width(word);
        if col > 0 && col + 1 + word_w > w {
            out.push(line.trim_end().to_string());
            line.clear();
            col = 0;
        }
        if col > 0 {
            line.push(' ');
            col += 1;
        }
        line.push_str(word);
        col += word_w;
    }
    if !line.is_empty() {
        out.push(line);
    }
    if out.is_empty() {
        out.push(String::new());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_loads() {
        let c = load_catalog().expect("catalog.json");
        assert!(!c.faculty.is_empty());
        assert!(!c.courses.is_empty());
    }
}
