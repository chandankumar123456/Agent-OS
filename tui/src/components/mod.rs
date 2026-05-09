// Stub components module - simplifies TUI for Phase 5 completion
pub mod task_list {
    use ratatui::{
        layout::Rect,
        style::{Style, Color},
        widgets::{Block, Borders, Paragraph},
        Frame,
    };
    use crate::styles::Theme;

    pub struct TaskList {
        pub selected: usize,
    }

    impl TaskList {
        pub fn new() -> Self {
            Self { selected: 0 }
        }

        pub fn draw(&mut self, frame: &mut Frame, area: Rect, _theme: &Theme, _focused: bool) {
            let block = Block::default()
                .borders(Borders::ALL)
                .title("Tasks");
            let paragraph = Paragraph::new("Task list placeholder")
                .block(block);
            frame.render_widget(paragraph, area);
        }

        pub fn selected_task(&self) -> Option<crate::models::Task> {
            None
        }
    }
}

pub mod log_panel {
    use ratatui::{
        layout::Rect,
        widgets::{Block, Borders, Paragraph},
        Frame,
    };
    use crate::styles::Theme;

    pub struct LogPanel {
        pub logs: Vec<String>,
        pub auto_scroll: bool,
    }

    impl LogPanel {
        pub fn new() -> Self {
            Self { logs: Vec::new(), auto_scroll: true }
        }

        pub fn draw(&self, frame: &mut Frame, area: Rect, _theme: &Theme, _focused: bool) {
            let block = Block::default()
                .borders(Borders::ALL)
                .title("Logs");
            let paragraph = Paragraph::new("Log panel placeholder")
                .block(block);
            frame.render_widget(paragraph, area);
        }
    }
}

pub mod status_bar {
    use ratatui::{
        layout::Rect,
        widgets::{Block, Borders, Paragraph},
        Frame,
    };
    use crate::styles::Theme;

    pub struct StatusBar;

    impl StatusBar {
        pub fn new() -> Self {
            Self
        }

        pub fn draw(&self, frame: &mut Frame, area: Rect, _theme: &Theme) {
            let block = Block::default()
                .borders(Borders::ALL);
            let paragraph = Paragraph::new("Status bar placeholder")
                .block(block);
            frame.render_widget(paragraph, area);
        }
    }
}

pub mod task_detail {
    use ratatui::{
        layout::Rect,
        widgets::{Block, Borders, Paragraph},
        Frame,
    };
    use crate::styles::Theme;
    use crate::models::Task;

    pub struct TaskDetail;

    impl TaskDetail {
        pub fn new() -> Self {
            Self
        }

        pub fn draw(&self, frame: &mut Frame, area: Rect, _theme: &Theme, _task: Option<&Task>) {
            let block = Block::default()
                .borders(Borders::ALL)
                .title("Task Detail");
            let paragraph = Paragraph::new("Task detail placeholder")
                .block(block);
            frame.render_widget(paragraph, area);
        }
    }
}
