//! UTETY campus terminal — app state, navigation, and rendering.

use crate::catalog::{Catalog, Course, Faculty, PaperCard};
use crate::consult::{self, ConsultHistoryTurn, ConsultResponse};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::sync::mpsc;
use std::thread;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap},
    Frame,
};
use std::cmp::{max, min};

const CHAMBERS: &[(&str, &str)] = &[
    ("1", "Great Hall"),
    ("2", "Faculty Wing"),
    ("3", "Course Registry"),
    ("4", "Research Stacks"),
    ("5", "Dispatch Archive"),
    ("6", "Admissions"),
    ("7", "Consultation"),
];

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Chamber {
    GreatHall,
    FacultyWing,
    CourseRegistry,
    ResearchStacks,
    DispatchArchive,
    Admissions,
    ConsultationStub,
}

impl Chamber {
    pub fn from_index(i: usize) -> Self {
        match i {
            0 => Self::GreatHall,
            1 => Self::FacultyWing,
            2 => Self::CourseRegistry,
            3 => Self::ResearchStacks,
            4 => Self::DispatchArchive,
            5 => Self::Admissions,
            _ => Self::ConsultationStub,
        }
    }

    pub fn index(self) -> usize {
        match self {
            Self::GreatHall => 0,
            Self::FacultyWing => 1,
            Self::CourseRegistry => 2,
            Self::ResearchStacks => 3,
            Self::DispatchArchive => 4,
            Self::Admissions => 5,
            Self::ConsultationStub => 6,
        }
    }

    pub fn label(self) -> &'static str {
        CHAMBERS[self.index()].1
    }
}

#[derive(Clone)]
pub struct ConsultationContext {
    pub professor: String,
    pub course_code: Option<String>,
}

#[derive(Clone)]
pub struct ConsultTurn {
    pub role: String,
    pub content: String,
}

pub struct ReaderState {
    pub title: String,
    pub file: String,
    pub lines: Vec<String>,
    pub scroll: usize,
}

pub struct App {
    pub catalog: Catalog,
    pub chamber: Chamber,
    pub tick: u64,
    pub gerald_stamp: bool,
    pub nav_focus: bool,
    pub list_index: usize,
    pub content_scroll: usize,
    pub filter: String,
    pub filter_active: bool,
    pub help_visible: bool,
    pub show_detail: bool,
    pub course_dept_tab: usize,
    pub reader: Option<ReaderState>,
    pub consultation: Option<ConsultationContext>,
    pub consult_input: String,
    pub consult_transcript: Vec<ConsultTurn>,
    pub consult_scroll: usize,
    pub consult_busy: bool,
    consult_rx: Option<mpsc::Receiver<ConsultResponse>>,
    pub should_quit: bool,
    pub status_msg: String,
}

impl App {
    pub fn new(catalog: Catalog) -> Self {
        Self {
            catalog,
            chamber: Chamber::GreatHall,
            tick: 0,
            gerald_stamp: false,
            nav_focus: false,
            list_index: 0,
            content_scroll: 0,
            filter: String::new(),
            filter_active: false,
            help_visible: false,
            show_detail: false,
            course_dept_tab: 0,
            reader: None,
            consultation: None,
            consult_input: String::new(),
            consult_transcript: Vec::new(),
            consult_scroll: 0,
            consult_busy: false,
            consult_rx: None,
            should_quit: false,
            status_msg: String::new(),
        }
    }

    pub fn mode_label(&self) -> String {
        if self.reader.is_some() {
            let t = self.reader.as_ref().map(|r| r.title.as_str()).unwrap_or("");
            return format!("[MODE: READING: {t}]");
        }
        if self.chamber == Chamber::ConsultationStub {
            if let Some(c) = &self.consultation {
                return format!("[MODE: CONSULTATION: {}]", c.professor);
            }
        }
        if self.filter_active {
            return format!("[MODE: FILTER: {}]", self.chamber.label());
        }
        format!("[MODE: BROWSING: {}]", self.chamber.label())
    }

    pub fn tick(&mut self) {
        self.tick = self.tick.wrapping_add(1);
        self.poll_consultation();
    }

    fn poll_consultation(&mut self) {
        let Some(rx) = self.consult_rx.take() else {
            return;
        };
        match rx.try_recv() {
            Ok(resp) => {
                self.consult_busy = false;
                if resp.ok {
                    let prof = self
                        .consultation
                        .as_ref()
                        .map(|c| c.professor.clone())
                        .unwrap_or_else(|| "Professor".into());
                    self.consult_transcript.push(ConsultTurn {
                        role: prof,
                        content: resp.text,
                    });
                    let tier = if resp.tier.is_empty() {
                        resp.provider
                    } else {
                        format!("{} ({})", resp.tier, resp.provider)
                    };
                    self.status_msg = format!("Consultation complete · {tier}");
                } else {
                    self.consult_transcript.push(ConsultTurn {
                        role: "System".into(),
                        content: format!("Consultation failed: {}", resp.error),
                    });
                    self.status_msg = format!("Consultation failed: {}", resp.error);
                }
                self.consult_scroll = usize::MAX;
            }
            Err(mpsc::TryRecvError::Empty) => {
                self.consult_rx = Some(rx);
            }
            Err(mpsc::TryRecvError::Disconnected) => {
                self.consult_busy = false;
                self.consult_transcript.push(ConsultTurn {
                    role: "System".into(),
                    content: "Consultation worker disconnected".into(),
                });
                self.status_msg = "Consultation worker disconnected".into();
            }
        }
    }

    pub fn handle_key(&mut self, key: KeyEvent) -> color_eyre::Result<()> {
        if key.kind != crossterm::event::KeyEventKind::Press {
            return Ok(());
        }

        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            self.should_quit = true;
            return Ok(());
        }

        if self.help_visible {
            self.help_visible = false;
            return Ok(());
        }

        if self.reader.is_some() {
            return self.handle_reader_key(key);
        }

        if self.filter_active {
            return self.handle_filter_key(key);
        }

        if self.chamber == Chamber::ConsultationStub && self.consultation.is_some() {
            return self.handle_consultation_key(key);
        }

        match key.code {
            KeyCode::Char('q') => self.should_quit = true,
            KeyCode::Char('?') => self.help_visible = true,
            KeyCode::Char('g') if self.chamber == Chamber::GreatHall => {
                self.gerald_stamp = !self.gerald_stamp;
                self.status_msg = if self.gerald_stamp {
                    "Gerald has approved the banner. Confetti is structural.".into()
                } else {
                    "Gerald resumes ordinary rotation.".into()
                };
            }
            KeyCode::Char('/') if self.chamber_has_filter() => {
                self.filter_active = true;
                self.filter.clear();
            }
            KeyCode::Esc => {
                if self.chamber == Chamber::ConsultationStub {
                    self.chamber = Chamber::FacultyWing;
                    self.consultation = None;
                } else if self.show_detail {
                    self.show_detail = false;
                    self.content_scroll = 0;
                } else {
                    self.nav_focus = false;
                }
            }
            KeyCode::Char(c @ '1'..='7') => {
                let idx = (c as u8 - b'1') as usize;
                if idx == 6 {
                    if self.consultation.is_some() {
                        self.chamber = Chamber::ConsultationStub;
                    } else {
                        self.status_msg = "Consultation: select a professor first (c)".into();
                    }
                } else {
                    self.chamber = Chamber::from_index(idx);
                    self.list_index = 0;
                    self.content_scroll = 0;
                    self.show_detail = false;
                    self.filter.clear();
                }
            }
            KeyCode::Tab => self.nav_focus = !self.nav_focus,
            KeyCode::Char('c') => self.open_consultation(),
            KeyCode::Enter => self.handle_enter()?,
            KeyCode::Char('[') if self.chamber == Chamber::CourseRegistry => {
                self.course_dept_tab = self.course_dept_tab.saturating_sub(1);
                self.list_index = 0;
                self.content_scroll = 0;
            }
            KeyCode::Char(']') if self.chamber == Chamber::CourseRegistry => {
                let max_tab = self.catalog.dept_tabs.len().saturating_sub(1);
                self.course_dept_tab = min(self.course_dept_tab + 1, max_tab);
                self.list_index = 0;
                self.content_scroll = 0;
            }
            KeyCode::Up | KeyCode::Char('k') => self.move_list(-1),
            KeyCode::Down | KeyCode::Char('j') => self.move_list(1),
            KeyCode::PageUp => self.content_scroll = self.content_scroll.saturating_sub(10),
            KeyCode::PageDown => {
                self.content_scroll = self.content_scroll.saturating_add(10);
            }
            _ => {}
        }
        Ok(())
    }

    fn handle_reader_key(&mut self, key: KeyEvent) -> color_eyre::Result<()> {
        let Some(r) = &mut self.reader else {
            return Ok(());
        };
        match key.code {
            KeyCode::Esc => self.reader = None,
            KeyCode::Up | KeyCode::Char('k') => r.scroll = r.scroll.saturating_sub(1),
            KeyCode::Down | KeyCode::Char('j') => {
                let max_scroll = r.lines.len().saturating_sub(1);
                r.scroll = min(r.scroll.saturating_add(1), max_scroll);
            }
            KeyCode::PageUp => r.scroll = r.scroll.saturating_sub(10),
            KeyCode::PageDown => {
                let max_scroll = r.lines.len().saturating_sub(1);
                r.scroll = min(r.scroll.saturating_add(10), max_scroll);
            }
            KeyCode::Home | KeyCode::Char('g') => r.scroll = 0,
            _ => {}
        }
        Ok(())
    }

    fn handle_filter_key(&mut self, key: KeyEvent) -> color_eyre::Result<()> {
        match key.code {
            KeyCode::Esc => {
                self.filter_active = false;
                self.filter.clear();
                self.list_index = 0;
            }
            KeyCode::Enter => {
                self.filter_active = false;
                self.list_index = 0;
            }
            KeyCode::Backspace => {
                self.filter.pop();
                self.list_index = 0;
            }
            KeyCode::Char(c) => {
                self.filter.push(c);
                self.list_index = 0;
            }
            _ => {}
        }
        Ok(())
    }

    fn chamber_has_filter(&self) -> bool {
        matches!(
            self.chamber,
            Chamber::FacultyWing | Chamber::CourseRegistry | Chamber::ResearchStacks | Chamber::DispatchArchive
        )
    }

    fn handle_consultation_key(&mut self, key: KeyEvent) -> color_eyre::Result<()> {
        match key.code {
            KeyCode::Char('q') => {
                self.consult_busy = false;
                self.consult_rx = None;
                self.should_quit = true;
            }
            KeyCode::Char('?') => self.help_visible = true,
            KeyCode::Esc => {
                self.chamber = Chamber::FacultyWing;
                self.consultation = None;
                self.consult_input.clear();
                self.consult_transcript.clear();
                self.consult_busy = false;
                self.consult_rx = None;
                self.status_msg = "Consultation cancelled".into();
            }
            KeyCode::Enter if !self.consult_busy => self.submit_consultation(),
            KeyCode::Backspace if !self.consult_busy => {
                self.consult_input.pop();
            }
            KeyCode::Char(c) if !self.consult_busy && !c.is_control() => {
                self.consult_input.push(c);
            }
            KeyCode::Up | KeyCode::Char('k') => {
                self.consult_scroll = self.consult_scroll.saturating_sub(1);
            }
            KeyCode::Down | KeyCode::Char('j') => {
                self.consult_scroll = self.consult_scroll.saturating_add(1);
            }
            KeyCode::PageUp => {
                self.consult_scroll = self.consult_scroll.saturating_sub(8);
            }
            KeyCode::PageDown => {
                self.consult_scroll = self.consult_scroll.saturating_add(8);
            }
            _ => {}
        }
        Ok(())
    }

    fn submit_consultation(&mut self) {
        let message = self.consult_input.trim().to_string();
        if message.is_empty() {
            return;
        }
        let Some(ctx) = self.consultation.clone() else {
            return;
        };

        self.consult_transcript.push(ConsultTurn {
            role: "user".into(),
            content: message.clone(),
        });
        self.consult_scroll = usize::MAX;
        self.consult_input.clear();
        self.consult_busy = true;
        self.status_msg = "Consulting... Esc cancels view; timeout protects the sidecar".into();

        let history: Vec<ConsultHistoryTurn> = self
            .consult_transcript
            .iter()
            .take(self.consult_transcript.len().saturating_sub(1))
            .map(|t| ConsultHistoryTurn {
                role: t.role.clone(),
                content: t.content.clone(),
            })
            .collect();
        let professor = ctx.professor.clone();
        let course_code = ctx.course_code.clone();
        let (tx, rx) = mpsc::channel();
        self.consult_rx = Some(rx);

        thread::spawn(move || {
            let resp = consult::run_consult(
                &professor,
                &message,
                course_code.as_deref(),
                &history,
            )
            .unwrap_or_else(|e| ConsultResponse {
                ok: false,
                error: e.to_string(),
                ..Default::default()
            });
            let _ = tx.send(resp);
        });
    }

    fn handle_enter(&mut self) -> color_eyre::Result<()> {
        match self.chamber {
            Chamber::GreatHall => {
                self.chamber = Chamber::FacultyWing;
                self.list_index = 0;
            }
            Chamber::FacultyWing | Chamber::CourseRegistry => {
                self.show_detail = !self.show_detail;
                self.content_scroll = 0;
            }
            Chamber::ResearchStacks => {
                if let Some(card) = self
                    .filtered_research()
                    .into_iter()
                    .nth(self.list_index)
                    .cloned()
                {
                    self.open_paper(&card)?;
                }
            }
            Chamber::DispatchArchive => {
                if let Some(card) = self
                    .filtered_dispatches()
                    .into_iter()
                    .nth(self.list_index)
                    .cloned()
                {
                    self.open_paper(&card)?;
                }
            }
            _ => {}
        }
        Ok(())
    }

    fn open_paper(&mut self, card: &PaperCard) -> color_eyre::Result<()> {
        let md = crate::catalog::load_paper(&card.file)?;
        let lines = crate::catalog::markdown_to_lines(&md, 72);
        self.reader = Some(ReaderState {
            title: card.title.clone(),
            file: card.file.clone(),
            lines,
            scroll: 0,
        });
        Ok(())
    }

    fn open_consultation(&mut self) {
        match self.chamber {
            Chamber::FacultyWing => {
                if let Some(f) = self.filtered_faculty().into_iter().nth(self.list_index) {
                    self.consultation = Some(ConsultationContext {
                        professor: f.name.clone(),
                        course_code: None,
                    });
                    self.reset_consultation_session();
                    self.chamber = Chamber::ConsultationStub;
                }
            }
            Chamber::CourseRegistry => {
                if let Some(c) = self.filtered_courses().into_iter().nth(self.list_index) {
                    self.consultation = Some(ConsultationContext {
                        professor: c.instructor.clone(),
                        course_code: Some(c.code.clone()),
                    });
                    self.reset_consultation_session();
                    self.chamber = Chamber::ConsultationStub;
                }
            }
            _ => {
                self.status_msg = "Consultation opens from Faculty or Courses (c)".into();
            }
        }
    }

    fn reset_consultation_session(&mut self) {
        self.consult_input.clear();
        self.consult_transcript.clear();
        self.consult_scroll = 0;
        self.consult_busy = false;
        self.consult_rx = None;
    }

    fn move_list(&mut self, delta: i32) {
        let len = self.current_list_len();
        if len == 0 {
            return;
        }
        let i = self.list_index as i32 + delta;
        self.list_index = max(0, min(len as i32 - 1, i)) as usize;
    }

    fn current_list_len(&self) -> usize {
        match self.chamber {
            Chamber::FacultyWing => self.filtered_faculty().len(),
            Chamber::CourseRegistry => self.filtered_courses().len(),
            Chamber::ResearchStacks => self.filtered_research().len(),
            Chamber::DispatchArchive => self.filtered_dispatches().len(),
            _ => 0,
        }
    }

    fn filtered_faculty(&self) -> Vec<&Faculty> {
        let q = self.filter.to_lowercase();
        self.catalog
            .faculty
            .iter()
            .filter(|f| {
                q.is_empty()
                    || f.name.to_lowercase().contains(&q)
                    || f.dept.to_lowercase().contains(&q)
            })
            .collect()
    }

    fn filtered_courses(&self) -> Vec<&Course> {
        let tab = &self.catalog.dept_tabs[self.course_dept_tab];
        let q = self.filter.to_lowercase();
        self.catalog
            .courses
            .iter()
            .filter(|c| {
                if c.code == "SSS 001" {
                    return false;
                }
                let dept_ok = tab.keys.as_ref().map_or(true, |keys| keys.contains(&c.dept_key));
                let q_ok = q.is_empty()
                    || c.code.to_lowercase().contains(&q)
                    || c.title.to_lowercase().contains(&q)
                    || c.instructor.to_lowercase().contains(&q);
                dept_ok && q_ok
            })
            .collect()
    }

    fn filtered_research(&self) -> Vec<&PaperCard> {
        filter_papers(&self.catalog.research, &self.filter)
    }

    fn filtered_dispatches(&self) -> Vec<&PaperCard> {
        filter_papers(&self.catalog.dispatches, &self.filter)
    }

    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1),
                Constraint::Min(3),
                Constraint::Length(1),
                Constraint::Length(1),
            ])
            .split(area);

        draw_title_bar(frame, chunks[0]);
        let body = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Length(24), Constraint::Min(20)])
            .split(chunks[1]);
        draw_nav(self, frame, body[0]);
        draw_main(self, frame, body[1]);
        draw_status(self, frame, chunks[2]);
        draw_footer(frame, chunks[3]);

        if self.help_visible {
            draw_help(frame, area);
        }
        if self.filter_active {
            draw_filter(frame, area, &self.filter);
        }
        if let Some(reader) = &self.reader {
            draw_reader(frame, area, reader);
        }
    }
}

fn filter_papers<'a>(papers: &'a [PaperCard], filter: &str) -> Vec<&'a PaperCard> {
    let q = filter.to_lowercase();
    papers
        .iter()
        .filter(|p| {
            q.is_empty()
                || p.title.to_lowercase().contains(&q)
                || p.label.to_lowercase().contains(&q)
        })
        .collect()
}

fn draw_title_bar(frame: &mut Frame, area: Rect) {
    let line = Line::from(vec![
        Span::styled(" UTETY ARCHIVAL TERMINAL ", Style::default().add_modifier(Modifier::BOLD)),
        Span::styled("· EST. 1095 ", Style::default().fg(Color::DarkGray)),
        Span::styled("· Non Veritas Sed Vibrae", Style::default().fg(Color::Yellow)),
    ]);
    frame.render_widget(Paragraph::new(line), area);
}

fn draw_nav(app: &App, frame: &mut Frame, area: Rect) {
    let items: Vec<ListItem> = CHAMBERS
        .iter()
        .enumerate()
        .map(|(i, (_, name))| {
            let active = app.chamber.index() == i;
            let prefix = if active { "▸ " } else { "  " };
            ListItem::new(format!("{prefix}{name}")).style(if active {
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            })
        })
        .collect();

    let block = Block::default()
        .borders(Borders::ALL)
        .title(" CAMPUS INDEX ")
        .border_style(Style::default().fg(Color::DarkGray));
    let list = List::new(items).block(block);
    frame.render_widget(list, area);
}

fn draw_main(app: &App, frame: &mut Frame, area: Rect) {
    match app.chamber {
        Chamber::GreatHall => draw_great_hall(app, frame, area),
        Chamber::FacultyWing => draw_faculty(app, frame, area),
        Chamber::CourseRegistry => draw_courses(app, frame, area),
        Chamber::ResearchStacks => draw_paper_list(app, frame, area, " RESEARCH STACKS ", true),
        Chamber::DispatchArchive => draw_paper_list(app, frame, area, " DISPATCH ARCHIVE ", false),
        Chamber::Admissions => draw_admissions(app, frame, area),
        Chamber::ConsultationStub => draw_consultation(app, frame, area),
    }
}

fn draw_great_hall(app: &App, frame: &mut Frame, area: Rect) {
    let m = &app.catalog.meta;
    let seal_frames = ["◎", "◉", "◌", "◍"];
    let seal = seal_frames[((app.tick / 4) as usize) % seal_frames.len()];
    let rotor_frames = ["|", "/", "-", "\\"];
    let rotor = rotor_frames[((app.tick / 2) as usize) % rotor_frames.len()];
    let shimmer = if (app.tick / 8) % 2 == 0 {
        Color::Yellow
    } else {
        Color::Rgb(184, 128, 32)
    };
    let motto = &m.mottos[((app.tick / 40) as usize) % m.mottos.len().max(1)];
    let whispers = [
        "THE RUG REMEMBERS",
        "THE DOOR REMAINS OPEN",
        "THE PIGEON KNOWS EVERY STOP",
        "THE ORANGE IS LISTENING",
        "ALL RIGHTS RESERVED RETROACTIVELY",
    ];
    let whisper = whispers[((app.tick / 70) as usize) % whispers.len()];

    let block = Block::default()
        .borders(Borders::ALL)
        .title(" GREAT HALL ")
        .border_style(Style::default().fg(shimmer));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(11),
            Constraint::Length(3),
            Constraint::Min(6),
            Constraint::Length(2),
        ])
        .split(inner);

    let hero = vec![
        Line::from(Span::styled(
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓",
            Style::default().fg(shimmer),
        )),
        Line::from(vec![
            Span::styled("┃ ", Style::default().fg(shimmer)),
            Span::styled("           THE UNIVERSITY OF TECHNICAL ENTROPY           ", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled(" ┃", Style::default().fg(shimmer)),
        ]),
        Line::from(vec![
            Span::styled("┃ ", Style::default().fg(shimmer)),
            Span::styled("                         THANK YOU                       ", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled(" ┃", Style::default().fg(shimmer)),
        ]),
        Line::from(Span::styled(
            "┃                                                            ┃",
            Style::default().fg(shimmer),
        )),
        Line::from(vec![
            Span::styled("┃ ", Style::default().fg(shimmer)),
            Span::styled("                 U  T  E  T  Y                 ", Style::default().fg(Color::Rgb(184, 128, 32)).add_modifier(Modifier::BOLD)),
            Span::styled("ΔΣ=42", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::styled(" ┃", Style::default().fg(shimmer)),
        ]),
        Line::from(vec![
            Span::styled("┃ ", Style::default().fg(shimmer)),
            Span::styled("            FOUNDED A.D. 1095 · ONE YEAR BEFORE OXFORD      ", Style::default().fg(Color::DarkGray)),
            Span::styled("┃", Style::default().fg(shimmer)),
        ]),
        Line::from(Span::styled(
            "┃                                                            ┃",
            Style::default().fg(shimmer),
        )),
        Line::from(vec![
            Span::styled("┃ ", Style::default().fg(shimmer)),
            Span::styled(format!("              {seal}  "), Style::default().fg(Color::Rgb(184, 128, 32))),
            Span::styled("THE SYLLABUS IS MENDATORY", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled(format!("  {seal}             "), Style::default().fg(Color::Rgb(184, 128, 32))),
            Span::styled("┃", Style::default().fg(shimmer)),
        ]),
        Line::from(Span::styled(
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
            Style::default().fg(shimmer),
        )),
    ];
    frame.render_widget(
        Paragraph::new(hero).alignment(Alignment::Center),
        rows[0],
    );

    let stats = m
        .stats
        .iter()
        .map(|s| format!(" {} {}", s.value, s.label))
        .collect::<Vec<_>>()
        .join("  · ");
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(Span::styled(stats, Style::default().fg(Color::Rgb(184, 128, 32)).add_modifier(Modifier::BOLD))),
            Line::from(vec![
                Span::styled("rotunda transmission: ", Style::default().fg(Color::DarkGray)),
                Span::styled(format!("«{motto}»"), Style::default().fg(Color::Cyan).italic()),
                Span::styled(format!("  ·  {whisper}"), Style::default().fg(Color::DarkGray)),
            ]),
        ])
        .alignment(Alignment::Center),
        rows[1],
    );

    let mut about = vec![
        Line::from(Span::styled(
            m.tagline.clone(),
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
    ];
    for para in wrap_line(&m.about, rows[2].width.saturating_sub(4) as usize) {
        about.push(Line::from(para));
    }
    about.push(Line::from(""));
    if app.gerald_stamp {
        about.push(Line::from(vec![
            Span::styled("[APPROVED] ", Style::default().fg(Color::Rgb(184, 128, 32)).add_modifier(Modifier::BOLD)),
            Span::styled("Gerald rotated once and the banner became retroactively official.", Style::default().fg(Color::Rgb(184, 128, 32)).italic()),
        ]));
        about.push(Line::from(Span::styled(
            format!("Confetti vector: f(x + 17π) {rotor} ΔΣ=42"),
            Style::default().fg(Color::DarkGray),
        )));
    } else {
        about.push(Line::from(Span::styled(
            m.gerald_quote.clone(),
            Style::default().fg(Color::Rgb(184, 128, 32)).italic(),
        )));
        about.push(Line::from(Span::styled(
            format!("Gerald rotation indicator: {rotor}"),
            Style::default().fg(Color::DarkGray),
        )));
    }

    frame.render_widget(
        Paragraph::new(about)
            .block(Block::default().borders(Borders::TOP).title(" CHARTER "))
            .wrap(Wrap { trim: true }),
        rows[2],
    );

    frame.render_widget(
        Paragraph::new(Span::styled(
            "Enter → Faculty Wing   ·   2 Faculty   ·   3 Courses   ·   4 Research   ·   5 Dispatches",
            Style::default().fg(Color::DarkGray),
        ))
        .alignment(Alignment::Center),
        rows[3],
    );
}

fn draw_faculty(app: &App, frame: &mut Frame, area: Rect) {
    let faculty = app.filtered_faculty();
    if app.show_detail {
        if let Some(f) = faculty.get(app.list_index) {
            draw_faculty_detail(app, frame, area, f);
            return;
        }
    }

    let items: Vec<ListItem> = faculty
        .iter()
        .enumerate()
        .map(|(i, f)| {
            let sel = i == app.list_index;
            ListItem::new(format!("{} — {}", f.name, f.dept)).style(if sel {
                Style::default().bg(Color::DarkGray).add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            })
        })
        .collect();

    let title = if app.filter.is_empty() {
        " FACULTY WING ".to_string()
    } else {
        format!(" FACULTY · /{} ", app.filter)
    };
    let block = Block::default()
        .borders(Borders::ALL)
        .title(title)
        .border_style(Style::default().fg(Color::Cyan));
    frame.render_widget(List::new(items).block(block), area);
}

fn draw_faculty_detail(app: &App, frame: &mut Frame, area: Rect, f: &Faculty) {
    let mut lines = vec![
        Line::from(Span::styled(
            f.name.clone(),
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            format!("{} · {}", f.dept, f.location),
            Style::default().fg(Color::DarkGray),
        )),
        Line::from(""),
    ];
    if !f.course.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("Course: {}", f.course),
            Style::default().fg(Color::Yellow),
        )));
        lines.push(Line::from(""));
    }
    for para in wrap_line(&f.bio, area.width.saturating_sub(4) as usize) {
        lines.push(Line::from(para));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "c → Consultation   Esc → list",
        Style::default().fg(Color::DarkGray),
    )));

    let visible = scroll_lines(&lines, app.content_scroll, area.height as usize);
    let block = Block::default()
        .borders(Borders::ALL)
        .title(format!(" {} — DOSSIER ", f.name))
        .border_style(Style::default().fg(Color::Cyan));
    frame.render_widget(Paragraph::new(visible).block(block), area);
}

fn draw_courses(app: &App, frame: &mut Frame, area: Rect) {
    let tab = &app.catalog.dept_tabs[app.course_dept_tab];
    let courses = app.filtered_courses();

    if app.show_detail {
        if let Some(c) = courses.get(app.list_index) {
            draw_course_detail(app, frame, area, c, &tab.label);
            return;
        }
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(1)])
        .split(area);

    let tab_line = format!(
        "Dept: {}  ([/] prev/next · {}/{})",
        tab.label,
        app.course_dept_tab + 1,
        app.catalog.dept_tabs.len()
    );
    frame.render_widget(
        Paragraph::new(tab_line).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" COURSE REGISTRY "),
        ),
        chunks[0],
    );

    let items: Vec<ListItem> = courses
        .iter()
        .enumerate()
        .map(|(i, c)| {
            let sel = i == app.list_index;
            ListItem::new(format!("{}  {} — {}", c.code, c.title, c.instructor)).style(if sel {
                Style::default().bg(Color::DarkGray).add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            })
        })
        .collect();

    frame.render_widget(List::new(items).block(Block::default().borders(Borders::LEFT | Borders::RIGHT | Borders::BOTTOM)), chunks[1]);
}

fn draw_course_detail(app: &App, frame: &mut Frame, area: Rect, c: &Course, dept: &str) {
    let mut lines = vec![
        Line::from(Span::styled(
            format!("{} — {}", c.code, c.title),
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            format!("{} · {} credits · {}", c.instructor, c.credits, dept),
            Style::default().fg(Color::DarkGray),
        )),
        Line::from(Span::styled(
            format!("Prereq: {}", c.prereq),
            Style::default().fg(Color::DarkGray),
        )),
    ];
    if let Some(cross) = &c.cross {
        lines.push(Line::from(Span::styled(
            format!("Cross-listed: {cross}"),
            Style::default().fg(Color::DarkGray),
        )));
    }
    lines.push(Line::from(""));
    for para in wrap_line(&c.desc, area.width.saturating_sub(4) as usize) {
        lines.push(Line::from(para));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "c → Enroll (consultation stub)   Esc → list",
        Style::default().fg(Color::DarkGray),
    )));

    let visible = scroll_lines(&lines, app.content_scroll, area.height as usize);
    let block = Block::default()
        .borders(Borders::ALL)
        .title(format!(" {} ", c.code))
        .border_style(Style::default().fg(Color::Yellow));
    frame.render_widget(Paragraph::new(visible).block(block), area);
}

fn draw_paper_list(app: &App, frame: &mut Frame, area: Rect, title: &str, research: bool) {
    let papers = if research {
        app.filtered_research()
    } else {
        app.filtered_dispatches()
    };

    let items: Vec<ListItem> = papers
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let sel = i == app.list_index;
            ListItem::new(format!("[{}] {}", p.label, p.title)).style(if sel {
                Style::default().bg(Color::DarkGray).add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            })
        })
        .collect();

    let block = Block::default()
        .borders(Borders::ALL)
        .title(title)
        .border_style(Style::default().fg(Color::Magenta));
    frame.render_widget(List::new(items).block(block), area);
}

fn draw_admissions(app: &App, frame: &mut Frame, area: Rect) {
    let mut lines = vec![
        Line::from(Span::styled(
            "Admissions",
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
    ];
    for sec in &app.catalog.admissions {
        lines.push(Line::from(Span::styled(
            sec.title.clone(),
            Style::default().fg(Color::Yellow),
        )));
        for para in wrap_line(&sec.body, area.width.saturating_sub(4) as usize) {
            lines.push(Line::from(para));
        }
        lines.push(Line::from(""));
    }
    lines.push(Line::from(Span::styled(
        "Ready to begin? Faculty Wing → choose advisor → c",
        Style::default().fg(Color::DarkGray),
    )));

    let visible = scroll_lines(&lines, app.content_scroll, area.height as usize);
    let block = Block::default()
        .borders(Borders::ALL)
        .title(" ADMISSIONS ")
        .border_style(Style::default().fg(Color::Green));
    frame.render_widget(Paragraph::new(visible).block(block), area);
}

fn draw_consultation(app: &App, frame: &mut Frame, area: Rect) {
    let ctx = app.consultation.as_ref();
    let prof = ctx.map(|c| c.professor.as_str()).unwrap_or("—");
    let course = ctx
        .and_then(|c| c.course_code.as_ref())
        .map(|s| s.as_str())
        .unwrap_or("");

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(4),
            Constraint::Length(3),
        ])
        .split(area);

    let mut header = vec![
        Line::from(Span::styled(
            format!("Professor: {prof}"),
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        )),
    ];
    if !course.is_empty() {
        header.push(Line::from(Span::styled(
            format!("Course: {course}"),
            Style::default().fg(Color::Yellow),
        )));
    } else {
        header.push(Line::from(Span::styled(
            "Office hours · local Ollama",
            Style::default().fg(Color::DarkGray),
        )));
    }
    frame.render_widget(
        Paragraph::new(header).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" CONSULTATION ")
                .border_style(Style::default().fg(Color::Rgb(184, 128, 32))),
        ),
        chunks[0],
    );

    let transcript_width = chunks[1].width.saturating_sub(4) as usize;
    let transcript_lines = consultation_transcript_lines(app, transcript_width);
    let transcript_height = chunks[1].height.saturating_sub(2) as usize;
    let scroll = clamped_scroll(app.consult_scroll, transcript_lines.len(), transcript_height);
    let visible = scroll_lines(&transcript_lines, scroll, chunks[1].height as usize);
    frame.render_widget(
        Paragraph::new(visible).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" TRANSCRIPT ")
                .border_style(Style::default().fg(Color::DarkGray)),
        ),
        chunks[1],
    );

    let prompt = if app.consult_busy {
        "Waiting for faculty…".to_string()
    } else {
        format!("> {}{}", app.consult_input, "█")
    };
    frame.render_widget(
        Paragraph::new(prompt).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" YOUR MESSAGE ")
                .border_style(Style::default().fg(Color::Green)),
        ),
        chunks[2],
    );
}

fn consultation_transcript_lines(app: &App, width: usize) -> Vec<Line<'static>> {
    let mut lines: Vec<Line> = Vec::new();
    if app.consult_transcript.is_empty() && !app.consult_busy {
        lines.push(Line::from(Span::styled(
            "Ask a question. Enter sends. Esc returns to campus.",
            Style::default().fg(Color::DarkGray),
        )));
    }

    for turn in &app.consult_transcript {
        push_wrapped_turn(&mut lines, turn, width);
        lines.push(Line::from(""));
    }

    if app.consult_busy {
        lines.push(Line::from(Span::styled(
            "... consulting (Esc cancels view; hard timeout will stop the sidecar)",
            Style::default().fg(Color::Rgb(184, 128, 32)),
        )));
    }

    lines.into_iter().map(|l| owned_line(&l)).collect()
}

fn push_wrapped_turn(lines: &mut Vec<Line>, turn: &ConsultTurn, width: usize) {
    let (label_text, label_style) = if turn.role == "user" {
        (
            "You: ".to_string(),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )
    } else {
        (
            format!("{}: ", turn.role),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )
    };

    let body_width = width.saturating_sub(label_text.len()).max(20);
    let paragraphs: Vec<&str> = if turn.content.is_empty() {
        vec![""]
    } else {
        turn.content.lines().collect()
    };

    for (para_i, para) in paragraphs.iter().enumerate() {
        let wrapped = wrap_line(para, body_width);
        for (line_i, wrapped_line) in wrapped.into_iter().enumerate() {
            if para_i == 0 && line_i == 0 {
                lines.push(Line::from(vec![
                    Span::styled(label_text.clone(), label_style),
                    Span::raw(wrapped_line),
                ]));
            } else {
                lines.push(Line::from(format!("  {wrapped_line}")));
            }
        }
    }
}

fn clamped_scroll(requested: usize, line_count: usize, viewport_height: usize) -> usize {
    let max_scroll = line_count.saturating_sub(viewport_height.max(1));
    min(requested, max_scroll)
}

fn draw_status(app: &App, frame: &mut Frame, area: Rect) {
    let msg = if app.status_msg.is_empty() {
        app.mode_label()
    } else {
        app.status_msg.clone()
    };
    frame.render_widget(
        Paragraph::new(Span::styled(msg, Style::default().fg(Color::DarkGray))),
        area,
    );
}

fn draw_footer(frame: &mut Frame, area: Rect) {
    let hints = " q quit · ? help · 1-7 chambers · / filter · c consult · Enter send/open · Esc back · Tab nav ";
    frame.render_widget(
        Paragraph::new(Span::styled(hints, Style::default().fg(Color::DarkGray))),
        area,
    );
}

fn draw_filter(frame: &mut Frame, area: Rect, filter: &str) {
    let popup = centered_rect(60, 3, area);
    frame.render_widget(
        Paragraph::new(format!("/{filter}_")).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" FILTER ")
                .border_style(Style::default().fg(Color::Cyan)),
        ),
        popup,
    );
}

fn draw_help(frame: &mut Frame, area: Rect) {
    let popup = centered_rect(70, 70, area);
    let text = vec![
        Line::from(Span::styled("UTETY Archival Terminal — Keys", Style::default().add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from("1-7     Jump to chamber"),
        Line::from("j/k ↑↓  Move selection"),
        Line::from("Enter   Open detail / paper / Faculty from Great Hall"),
        Line::from("/       Filter list (Faculty, Courses, Research, Dispatches)"),
        Line::from("c       Open Consultation (Faculty or Courses)"),
        Line::from("        In chamber: type message, Enter send, Esc back"),
        Line::from("[ / ]   Course dept tabs"),
        Line::from("PgUp/Dn Scroll detail / admissions"),
        Line::from("Tab     Toggle nav focus"),
        Line::from("?       This help"),
        Line::from("q       Quit"),
        Line::from(""),
        Line::from(Span::styled("Any key closes help", Style::default().fg(Color::DarkGray))),
    ];
    frame.render_widget(
        Paragraph::new(text).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" HELP ")
                .border_style(Style::default().fg(Color::Yellow)),
        ),
        popup,
    );
}

fn draw_reader(frame: &mut Frame, area: Rect, reader: &ReaderState) {
    let popup = centered_rect(90, 90, area);
    let inner = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(1)])
        .split(popup);

    let height = inner[1].height.saturating_sub(2) as usize;
    let start = reader.scroll;
    let end = min(reader.lines.len(), start + height);
    let body: Vec<Line> = reader.lines[start..end]
        .iter()
        .map(|l| Line::from(l.clone()))
        .collect();

    frame.render_widget(
        Paragraph::new(format!("{}\n{}", reader.file, reader.title)).block(
            Block::default()
                .borders(Borders::ALL)
                .title(" READING ")
                .border_style(Style::default().fg(Color::Magenta)),
        ),
        inner[0],
    );
    frame.render_widget(
        Paragraph::new(body).block(Block::default().borders(Borders::ALL)),
        inner[1],
    );
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

fn wrap_line(text: &str, width: usize) -> Vec<String> {
    crate::catalog::markdown_to_lines(text, width)
        .into_iter()
        .filter(|l| !l.is_empty())
        .collect()
}

fn scroll_lines(lines: &[Line], scroll: usize, height: usize) -> Vec<Line<'static>> {
    let h = height.saturating_sub(2).max(1);
    lines
        .iter()
        .skip(scroll)
        .take(h)
        .map(owned_line)
        .collect()
}

fn owned_line(l: &Line<'_>) -> Line<'static> {
    use std::borrow::Cow;
    Line::from(
        l.spans
            .iter()
            .map(|s| Span {
                content: Cow::Owned(s.content.to_string()),
                style: s.style,
                ..Default::default()
            })
            .collect::<Vec<_>>(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line_text(line: &Line<'_>) -> String {
        line.spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<Vec<_>>()
            .join("")
    }

    #[test]
    fn consultation_turns_wrap_to_transcript_width() {
        let turn = ConsultTurn {
            role: "user".into(),
            content: "this is a long prompt that should wrap across several visible transcript rows"
                .into(),
        };
        let mut lines = Vec::new();

        push_wrapped_turn(&mut lines, &turn, 30);

        assert!(lines.len() > 1);
        assert!(line_text(&lines[0]).starts_with("You: this is a long"));
        assert!(line_text(&lines[1]).starts_with("  "));
    }

    #[test]
    fn bottom_scroll_clamps_to_last_visible_window() {
        assert_eq!(clamped_scroll(usize::MAX, 3, 10), 0);
        assert_eq!(clamped_scroll(usize::MAX, 25, 10), 15);
        assert_eq!(clamped_scroll(7, 25, 10), 7);
    }
}
