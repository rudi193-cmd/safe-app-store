//! UTETY Archival Terminal — entry point.

use color_eyre::Result;
use crossterm::event::{self, Event};
use ratatui::DefaultTerminal;
use std::time::{Duration, Instant};
use utety_campus::app::App;
use utety_campus::catalog::load_catalog;

fn main() -> Result<()> {
    color_eyre::install()?;
    let catalog = load_catalog()?;
    let mut terminal = ratatui::init();
    let result = run(&mut terminal, App::new(catalog));
    ratatui::restore();
    result
}

fn run(terminal: &mut DefaultTerminal, mut app: App) -> Result<()> {
    let tick = Duration::from_millis(100);
    let mut last_tick = Instant::now();

    loop {
        terminal.draw(|frame| app.draw(frame))?;

        let timeout = tick.saturating_sub(last_tick.elapsed());
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                app.handle_key(key)?;
            }
        }
        if last_tick.elapsed() >= tick {
            app.tick();
            last_tick = Instant::now();
        }

        if app.should_quit {
            break;
        }
    }
    Ok(())
}
