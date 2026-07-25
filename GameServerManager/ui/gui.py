from __future__ import annotations

import os
import re
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from models import ACTIONS, ServerInfo
from core.backup_manager import BackupManager, BackupRecord, format_size
from core.process_manager import ProcessManager
from core.server_manager import ServerManager
from core.server_types import (
    get_server_type,
    get_server_type_name,
    is_minecraft_server,
    supports_ctrl_break_stop,
)
from core.paths import PROJECT_ROOT
from core.notification_manager import NtfySettings, NotificationManager
from core.task_scheduler import TaskSchedulerManager

try:
    import psutil
except ImportError:  # The application remains usable without optional live metrics.
    psutil = None
from core.settings_manager import AppSettings, SettingsManager
from core.update_manager import UpdateManager


SCRIPT_ACTIONS = ("start", "stop", "update")


ACTION_LABELS = {
    "start": "Start",
    "stop": "Stop",
    "restart": "Restart",
    "update": "Update",
}


class GameServerManagerApp(tk.Tk):
    def __init__(self, initial_command: str = "show") -> None:
        super().__init__()

        self.title("Game Server Manager")
        self.geometry("1380x820")
        self.minsize(1120, 680)

        self.manager = ServerManager()
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()
        self.task_scheduler = TaskSchedulerManager(PROJECT_ROOT)
        self.notifications = NotificationManager(self.settings.ntfy_settings())
        self.initial_command = initial_command

        self.selected_id: str | None = None
        self.busy: set[str] = set()
        self.console_lines: dict[str, list[str]] = {}
        self.player_status: dict[str, tuple[int, int | None, list[str]]] = {}
        self.last_player_query: dict[str, float] = {}
        self.console_line_limit = 5000

        self.processes = ProcessManager(
            output_callback=self._queue_output,
            exit_callback=self._queue_exit,
        )
        self.backups = BackupManager(self.settings.backup_root)
        self.updates = UpdateManager(self.backups, self.processes)
        self.backup_records: dict[str, BackupRecord] = {}

        self._build_ui()
        self._reload()

        self.after(1000, self._poll)
        self.after(700, lambda: self.handle_external_command(self.initial_command))

    def report_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self._notify_error_async("Unhandled application exception", details)
        messagebox.showerror(
            "Unexpected error",
            f"{exc_value}\n\nMore details are available in the log folder.",
            parent=self,
        )

    def _notify_error_async(self, title: str, details: str) -> None:
        if not self.settings.ntfy_enabled:
            return
        manager = NotificationManager(self.settings.ntfy_settings())
        def worker() -> None:
            try:
                manager.send_error(title, details)
            except Exception as notification_error:
                self._queue_output("__application__", f"[NTFY ERROR] {notification_error}")
        threading.Thread(target=worker, daemon=True).start()

    def _build_ui(self) -> None:
        header = ttk.Frame(
            self,
            padding=12,
        )
        header.pack(fill="x")

        ttk.Label(
            header,
            text="Game Server Manager",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")

        ttk.Button(
            header,
            text="Settings...",
            command=self._open_settings_dialog,
        ).pack(side="right")

        pane = ttk.PanedWindow(
            self,
            orient="horizontal",
        )
        pane.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=(0, 12),
        )

        left_panel = ttk.Frame(
            pane,
            padding=8,
        )
        right_panel = ttk.Frame(
            pane,
            padding=8,
        )

        pane.add(left_panel, weight=1)
        pane.add(right_panel, weight=3)

        self.server_tree = ttk.Treeview(
            left_panel,
            columns=("type", "state"),
            show="tree headings",
        )

        self.server_tree.heading(
            "#0",
            text="Name",
        )
        self.server_tree.heading(
            "type",
            text="Type",
        )
        self.server_tree.heading(
            "state",
            text="Status",
        )

        self.server_tree.column(
            "#0",
            width=230,
        )
        self.server_tree.column(
            "type",
            width=145,
        )
        self.server_tree.column(
            "state",
            width=125,
        )

        self.server_tree.pack(
            fill="both",
            expand=True,
        )

        self.server_tree.bind(
            "<<TreeviewSelect>>",
            self._on_server_selected,
        )

        left_buttons = ttk.Frame(left_panel)
        left_buttons.pack(
            fill="x",
            pady=8,
        )
        left_buttons.columnconfigure(0, weight=1)
        left_buttons.columnconfigure(1, weight=1)

        ttk.Button(
            left_buttons,
            text="Set active",
            command=self._set_active_server,
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )

        ttk.Button(
            left_buttons,
            text="Add server...",
            command=self._add_server,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )

        ttk.Button(
            left_buttons,
            text="Remove server...",
            command=self._remove_server,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )

        live_frame = ttk.LabelFrame(
            left_panel,
            text="Live server status",
            padding=10,
        )
        live_frame.pack(fill="x", pady=(0, 8))

        self.live_players_var = tk.StringVar(value="Players: no server selected")
        self.live_names_var = tk.StringVar(value="Player names: none")
        self.live_server_resource_var = tk.StringVar(value="Server process: unavailable")
        self.live_system_resource_var = tk.StringVar(value="System: collecting data...")

        for variable in (
            self.live_players_var,
            self.live_names_var,
            self.live_server_resource_var,
            self.live_system_resource_var,
        ):
            ttk.Label(
                live_frame,
                textvariable=variable,
                wraplength=380,
                justify="left",
            ).pack(anchor="w", fill="x", pady=2)

        self.server_name_var = tk.StringVar(
            value="No server selected"
        )
        self.server_status_var = tk.StringVar()

        ttk.Label(
            right_panel,
            textvariable=self.server_name_var,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            right_panel,
            textvariable=self.server_status_var,
        ).pack(anchor="w")

        control_frame = ttk.LabelFrame(
            right_panel,
            text="Server controls",
            padding=8,
        )
        control_frame.pack(
            fill="x",
            pady=8,
        )

        self.action_buttons: dict[str, ttk.Button] = {}

        button_definitions = [
            ("start", "▶ Start"),
            ("stop", "■ Stop"),
            ("restart", "↻ Restart"),
            ("update", "⬇ Update"),
        ]

        for column, (action, label) in enumerate(button_definitions):
            button = ttk.Button(
                control_frame,
                text=label,
                command=lambda selected_action=action: self._run_action(
                    selected_action
                ),
            )

            button.grid(
                row=0,
                column=column,
                padx=4,
            )

            self.action_buttons[action] = button

        tools_frame = ttk.Frame(right_panel)
        tools_frame.pack(fill="x")

        ttk.Button(
            tools_frame,
            text="Rescan",
            command=self._refresh_server,
        ).pack(side="left")

        ttk.Button(
            tools_frame,
            text="Open folder",
            command=self._open_server_folder,
        ).pack(
            side="left",
            padx=8,
        )

        self.notebook = ttk.Notebook(right_panel)
        self.notebook.pack(
            fill="both",
            expand=True,
            pady=(8, 0),
        )

        self.overview_tab = ttk.Frame(
            self.notebook,
            padding=10,
        )
        self.notebook.add(
            self.overview_tab,
            text="Overview",
        )

        self.script_tab = ttk.Frame(
            self.notebook,
            padding=10,
        )
        self.notebook.add(
            self.script_tab,
            text="Scripts",
        )

        self._build_script_tab()

        self._build_console_tab()
        self.plugins_list = self._create_list_tab(
            self.notebook,
            "Plugins",
        )
        self.worlds_list = self._create_list_tab(
            self.notebook,
            "Worlds",
        )
        self.health_tree = self._create_health_tab()
        self.files_list = self._create_list_tab(
            self.notebook,
            "Detected files",
        )

        self._build_backup_tab()

        self._tab_order = [
            (self.overview_tab, "Overview", None),
            (self.script_tab, "Scripts", None),
            (self.console_tab, "Console", None),
            (self.plugins_list.master, "Plugins", "plugins"),
            (self.worlds_list.master, "Worlds", "worlds"),
            (self.health_tree.master.master if isinstance(self.health_tree.master, ttk.Frame) else self.health_tree.master, "Health checks", None),
            (self.files_list.master, "Detected files", None),
            (self.backup_tab, "Backups", None),
        ]

    def _update_visible_tabs(self, server_type: str) -> None:
        """Shows only tabs supported by the selected server type."""
        definition = get_server_type(server_type)
        selected = self.notebook.select()
        selected_widget = self.notebook.nametowidget(selected) if selected else None

        # Rebuild the tab order to avoid disabled or empty Minecraft-specific pages.
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)

        for frame, title, capability in self._tab_order:
            if capability == "plugins" and not definition.supports_plugins:
                continue
            if capability == "worlds" and not definition.supports_worlds:
                continue
            self.notebook.add(frame, text=title)

        visible = [self.notebook.nametowidget(tab) for tab in self.notebook.tabs()]
        if selected_widget in visible:
            self.notebook.select(selected_widget)
        elif visible:
            self.notebook.select(visible[0])

        # A world-only backup is meaningful only for server types with worlds.
        if hasattr(self, "world_backup_button"):
            self.world_backup_button.configure(
                state="normal" if definition.supports_worlds else "disabled"
            )

    def _build_backup_tab(self) -> None:
        self.backup_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.backup_tab, text="Backups")

        toolbar = ttk.Frame(self.backup_tab)
        toolbar.pack(fill="x", pady=(0, 8))

        ttk.Button(
            toolbar,
            text="Create full backup",
            command=lambda: self._create_backup("full"),
        ).pack(side="left")
        self.world_backup_button = ttk.Button(
            toolbar,
            text="Create world backup",
            command=lambda: self._create_backup("world"),
        )
        self.world_backup_button.pack(side="left", padx=8)
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self._refresh_backups,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Open backup folder",
            command=self._open_backup_folder,
        ).pack(side="right")

        self.backup_tree = ttk.Treeview(
            self.backup_tab,
            columns=("created", "type", "reason", "size", "files"),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "created": "Created",
            "type": "Type",
            "reason": "Reason",
            "size": "Size",
            "files": "Files",
        }
        widths = {"created": 145, "type": 120, "reason": 330, "size": 90, "files": 70}
        for column, title in headings.items():
            self.backup_tree.heading(column, text=title)
            self.backup_tree.column(column, width=widths[column], anchor="w")
        self.backup_tree.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.backup_tab)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(
            bottom,
            text="Delete selected backup",
            command=self._delete_selected_backup,
        ).pack(side="right")

        self.backup_status_var = tk.StringVar(value="No server selected.")
        ttk.Label(bottom, textvariable=self.backup_status_var).pack(side="left")

    def _create_backup(self, backup_type: str) -> None:
        server = self._selected_server()
        if server is None:
            return
        if self.processes.is_running(server.id):
            messagebox.showwarning(
                "Server is running",
                "The server must be stopped to create a consistent backup.",
            )
            return
        label = "Full backup" if backup_type == "full" else "World backup"
        if not messagebox.askyesno(label, f"Create {label.lower()} for {server.name}?"):
            return
        self.busy.add(server.id)
        self._update_buttons(server)
        self.backup_status_var.set(f"Creating {label.lower()}...")
        threading.Thread(
            target=self._backup_worker,
            args=(server, backup_type, label),
            daemon=True,
        ).start()

    def _backup_worker(self, server: ServerInfo, backup_type: str, label: str) -> None:
        try:
            record = self.backups.create_backup(
                server,
                backup_type=backup_type,
                reason=f"Manual {label}",
                progress_callback=lambda path, current, total: self.after(
                    0,
                    lambda p=path, c=current, t=total: self.backup_status_var.set(
                        f"{label}: {c}/{t} – {p}"
                    ),
                ),
            )
            self.after(0, lambda r=record: self._backup_finished(server, r, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._backup_finished(server, None, error))

    def _backup_finished(
        self,
        server: ServerInfo,
        record: BackupRecord | None,
        error: Exception | None,
    ) -> None:
        self.busy.discard(server.id)
        if error:
            self.backup_status_var.set("Backup failed.")
            messagebox.showerror("Backup failed", str(error))
        elif record:
            self.backup_status_var.set(
                f"Backup created: {format_size(record.size_bytes)}, {record.file_count} files"
            )
            messagebox.showinfo("Backup", "The backup was created successfully.")
        self._refresh_backups()
        self._reload(server.id)

    def _refresh_backups(self) -> None:
        if not hasattr(self, "backup_tree"):
            return
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        self.backup_records.clear()
        server = self._selected_server()
        if server is None:
            self.backup_status_var.set("No server selected.")
            return
        records = self.backups.list_backups(server.id)
        for record in records:
            iid = record.id
            self.backup_records[iid] = record
            self.backup_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    record.created_display,
                    self._backup_type_label(record.backup_type),
                    record.reason,
                    format_size(record.size_bytes),
                    record.file_count,
                ),
            )
        used = self.backups.storage_used(server.id)
        self.backup_status_var.set(f"{len(records)} backup(s) – {format_size(used)} of 50 GB used.")

    def _delete_selected_backup(self) -> None:
        selection = self.backup_tree.selection()
        if not selection:
            return
        record = self.backup_records.get(selection[0])
        if record is None:
            return
        if not messagebox.askyesno(
            "Delete backup",
            f"Delete the backup from {record.created_display}?",
        ):
            return
        try:
            self.backups.delete_backup(record)
            self._refresh_backups()
        except Exception as exc:
            messagebox.showerror("Delete failed", str(exc))

    def _open_backup_folder(self) -> None:
        server = self._selected_server()
        folder = self.backups.backup_root / server.id if server else self.backups.backup_root
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    @staticmethod
    def _backup_type_label(backup_type: str) -> str:
        return {
            "full": "Full backup",
            "world": "World backup",
            "plugin_update": "Plugin update",
            "server_update": "Server update",
            "manual": "Manual",
        }.get(backup_type, backup_type)

    def _build_script_tab(self) -> None:
        self.script_vars = {action: tk.StringVar() for action in SCRIPT_ACTIONS}
        self.backup_paths_list: tk.Listbox | None = None

        descriptions = {
            "start": (
                "Required. Select the script in the server folder. The selected "
                "path is stored automatically; the file is not copied."
            ),
            "stop": (
                "Optional for Minecraft and Windrose. Minecraft uses the console "
                "command 'stop'; Windrose stops the exact managed process tree by "
                "PID. A Windrose stop script is therefore not required."
            ),
            "update": (
                "Optional. Select an update script inside the server folder. The "
                "selection is stored immediately and the script remains in place."
            ),
        }

        ttk.Label(
            self.script_tab,
            text=(
                "Only paths are stored. Scripts remain inside the selected server folder "
                "and are never copied into Game Server Manager. Restart always performs "
                "Stop followed by Start."
            ),
            wraplength=780,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        row = 1
        for action in SCRIPT_ACTIONS:
            ttk.Label(
                self.script_tab,
                text=f"{ACTION_LABELS[action]} script:",
                font=("Segoe UI", 10, "bold"),
            ).grid(row=row, column=0, sticky="nw", pady=(4, 0))

            ttk.Entry(
                self.script_tab,
                textvariable=self.script_vars[action],
                width=65,
                state="readonly",
            ).grid(row=row, column=1, sticky="ew", padx=8, pady=(4, 0))

            button_frame = ttk.Frame(self.script_tab)
            button_frame.grid(row=row, column=2, sticky="w", pady=(4, 0))
            ttk.Button(
                button_frame,
                text="Browse",
                command=lambda selected_action=action: self._choose_script(selected_action),
            ).pack(side="left")
            ttk.Button(
                button_frame,
                text="Clear",
                command=lambda selected_action=action: self._clear_script(selected_action),
            ).pack(side="left", padx=(5, 0))

            ttk.Label(
                self.script_tab,
                text=descriptions[action],
                wraplength=680,
                foreground="#555555",
            ).grid(row=row + 1, column=1, columnspan=2, sticky="w", padx=8, pady=(2, 12))
            row += 2

        self.script_tab.columnconfigure(1, weight=1)

        ttk.Separator(self.script_tab, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(8, 14)
        )
        row += 1
        ttk.Label(
            self.script_tab,
            text="Backup selection for non-Minecraft servers:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=row, column=0, sticky="nw")

        backup_frame = ttk.Frame(self.script_tab)
        backup_frame.grid(row=row, column=1, columnspan=2, sticky="nsew", padx=8)
        backup_scroll = ttk.Scrollbar(backup_frame, orient="vertical")
        backup_scroll.pack(side="right", fill="y")
        self.backup_paths_list = tk.Listbox(
            backup_frame,
            height=6,
            font=("Consolas", 9),
            yscrollcommand=backup_scroll.set,
        )
        self.backup_paths_list.pack(side="left", fill="both", expand=True)
        backup_scroll.configure(command=self.backup_paths_list.yview)
        row += 1

        ttk.Label(
            self.script_tab,
            text=(
                "Select several files at once and add folders as needed. All selected "
                "items must be inside the server folder. The selection is stored when "
                "the dialog is confirmed."
            ),
            wraplength=680,
            foreground="#555555",
        ).grid(row=row, column=1, columnspan=2, sticky="w", padx=8, pady=(3, 8))
        row += 1
        self.backup_select_button = ttk.Button(
            self.script_tab,
            text="Select backup files and folders...",
            command=self._open_backup_selection,
        )
        self.backup_select_button.grid(row=row, column=1, sticky="e", pady=(0, 12))

    def _build_console_tab(self) -> None:
        self.console_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.console_tab, text="Console")

        toolbar = ttk.Frame(self.console_tab)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(
            toolbar,
            text=(
                "Enter server commands without a leading slash. Commands are available "
                "while a server started by this manager is running."
            ),
            wraplength=760,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            toolbar,
            text="Clear console",
            command=self._clear_console,
        ).pack(side="right", padx=(8, 0))

        text_frame = ttk.Frame(self.console_tab)
        text_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.console_text = tk.Text(
            text_frame,
            state="disabled",
            font=("Consolas", 9),
            wrap="word",
            yscrollcommand=scrollbar.set,
        )
        self.console_text.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.console_text.yview)

        command_frame = ttk.Frame(self.console_tab)
        command_frame.pack(fill="x", pady=(8, 0))
        ttk.Label(command_frame, text="Command:").pack(side="left")
        self.console_command_var = tk.StringVar()
        self.console_command_entry = ttk.Entry(
            command_frame, textvariable=self.console_command_var
        )
        self.console_command_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.console_command_entry.bind("<Return>", self._send_console_command)
        self.console_send_button = ttk.Button(
            command_frame, text="Send", command=self._send_console_command
        )
        self.console_send_button.pack(side="right")
        self._set_console_input_state(False)

    def _set_console_input_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.console_command_entry.configure(state=state)
        self.console_send_button.configure(state=state)

    def _send_console_command(self, _event: tk.Event | None = None) -> str:
        server = self._selected_server()
        command = self.console_command_var.get().strip()
        if server is None or not command:
            return "break"
        try:
            self.processes.send_command(server.id, command)
        except Exception as exc:
            messagebox.showerror("Command failed", str(exc))
            return "break"
        self.console_command_var.set("")
        self._append_console(server.id, f"> {command}")
        return "break"

    def _create_text_tab(
        self,
        notebook: ttk.Notebook,
        title: str,
    ) -> tk.Text:
        frame = ttk.Frame(
            self.notebook,
            padding=8,
        )
        self.notebook.add(
            frame,
            text=title,
        )

        text_widget = tk.Text(
            frame,
            state="disabled",
            font=("Consolas", 9),
            wrap="word",
        )
        text_widget.pack(
            fill="both",
            expand=True,
        )

        return text_widget

    def _create_health_tab(self) -> ttk.Treeview:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="Health checks")

        summary = ttk.Label(
            frame,
            text="Server checks are refreshed whenever the server is rescanned.",
            foreground="#555555",
        )
        summary.pack(fill="x", pady=(0, 8))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        tree = ttk.Treeview(
            tree_frame,
            columns=("status", "check"),
            show="headings",
            yscrollcommand=scrollbar.set,
            selectmode="browse",
        )
        tree.heading("status", text="Status")
        tree.heading("check", text="Check")
        tree.column("status", width=120, minwidth=100, stretch=False, anchor="w")
        tree.column("check", width=650, minwidth=300, stretch=True, anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=tree.yview)

        tree.tag_configure("ok", foreground="#167c2c")
        tree.tag_configure("warning", foreground="#9a6500")
        tree.tag_configure("error", foreground="#b00020")
        tree.tag_configure("info", foreground="#245c9b")
        return tree

    def _create_list_tab(
        self,
        notebook: ttk.Notebook,
        title: str,
    ) -> tk.Listbox:
        frame = ttk.Frame(
            self.notebook,
            padding=8,
        )
        self.notebook.add(
            frame,
            text=title,
        )

        listbox = tk.Listbox(
            frame,
            font=("Segoe UI", 10),
        )
        listbox.pack(
            fill="both",
            expand=True,
        )

        return listbox

    def _reload(
        self,
        target_id: str | None = None,
    ) -> None:
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)

        for server in self.manager.servers:
            name = (
                f"{'★ ' if server.active else ''}"
                f"{server.name}"
            )

            self.server_tree.insert(
                "",
                "end",
                iid=server.id,
                text=name,
                values=(
                    self._friendly_server_type(
                        server.server_type
                    ),
                    self._server_state(server),
                ),
            )

        target_id = target_id or self.selected_id

        if (
            target_id
            and self.server_tree.exists(target_id)
        ):
            self.server_tree.selection_set(target_id)
            self.server_tree.focus(target_id)

            self._display_server(
                self.manager.get_server(target_id)
            )

        elif self.manager.servers:
            server = self.manager.servers[0]

            self.server_tree.selection_set(server.id)
            self.server_tree.focus(server.id)

            self._display_server(server)

        else:
            self._display_server(None)

    def _display_server(
        self,
        server: ServerInfo | None,
    ) -> None:
        for widget in self.overview_tab.winfo_children():
            widget.destroy()

        for listbox in (
            self.plugins_list,
            self.worlds_list,
            self.files_list,
        ):
            listbox.delete(0, tk.END)
        for item in self.health_tree.get_children():
            self.health_tree.delete(item)

        if server is None:
            self.selected_id = None
            self.server_name_var.set(
                "No server selected"
            )
            self.server_status_var.set("")
            self._clear_console()
            self._set_console_input_state(False)
            self.live_players_var.set("Players: no server selected")
            self.live_names_var.set("Player names: none")
            self.live_server_resource_var.set("Server process: unavailable")
            self.live_system_resource_var.set("System: collecting data...")
            return

        self.selected_id = server.id
        self.server_name_var.set(server.name)
        self.server_status_var.set(
            self._server_state(server)
        )

        rows: list[tuple[str, object]] = [
            (
                "Type",
                self._friendly_server_type(
                    server.server_type
                ),
            ),
            (
                "Path",
                server.path,
            ),
        ]

        rows.extend(server.properties.items())

        for row, (key, value) in enumerate(rows):
            ttk.Label(
                self.overview_tab,
                text=f"{key}:",
                font=("Segoe UI", 10, "bold"),
            ).grid(
                row=row,
                column=0,
                sticky="nw",
                padx=(0, 12),
                pady=3,
            )

            if value is True:
                display_value = "Active"
            elif value is False:
                display_value = "Disabled"
            else:
                display_value = str(value)

            ttk.Label(
                self.overview_tab,
                text=display_value,
                wraplength=700,
            ).grid(
                row=row,
                column=1,
                sticky="nw",
                pady=3,
            )

        for action in SCRIPT_ACTIONS:
            self.script_vars[action].set(
                server.action_scripts.get(
                    action,
                    "",
                )
            )

        if self.backup_paths_list is not None:
            self.backup_paths_list.delete(0, tk.END)
            for backup_path in server.backup_paths:
                self.backup_paths_list.insert(tk.END, backup_path)
            backup_state = "disabled" if is_minecraft_server(server.server_type) else "normal"
            self.backup_paths_list.configure(state=backup_state)
            self.backup_select_button.configure(state=backup_state)

        self._update_visible_tabs(server.server_type)

        self._fill_list(
            self.plugins_list,
            server.plugins,
            "No plugins detected.",
        )
        self._fill_list(
            self.worlds_list,
            server.worlds,
            "No worlds detected.",
        )
        self._fill_list(
            self.files_list,
            server.detected_files,
            "No files detected.",
        )

        status_labels = {
            "ok": "✓ OK",
            "warning": "⚠ Warning",
            "error": "✖ Error",
            "info": "ℹ Info",
        }
        if server.health_checks:
            ordered_checks = sorted(
                server.health_checks,
                key=lambda item: {"error": 0, "warning": 1, "info": 2, "ok": 3}.get(item.level, 4),
            )
            for check in ordered_checks:
                self.health_tree.insert(
                    "",
                    tk.END,
                    values=(status_labels.get(check.level, "• Info"), check.message),
                    tags=(check.level,),
                )
        else:
            self.health_tree.insert(
                "",
                tk.END,
                values=("ℹ Info", "No health check results."),
                tags=("info",),
            )

        self.console_text.configure(
            state="normal"
        )
        self.console_text.delete(
            "1.0",
            tk.END,
        )
        self.console_text.insert(
            tk.END,
            "\n".join(
                self.console_lines.get(
                    server.id,
                    [],
                )
            ),
        )
        self.console_text.configure(
            state="disabled"
        )

        self._update_buttons(server)
        self._set_console_input_state(self.processes.is_running(server.id))
        self._update_live_status(server)
        self._refresh_backups()

    def _fill_list(
        self,
        listbox: tk.Listbox,
        values: list[str],
        empty_text: str,
    ) -> None:
        if not values:
            listbox.insert(
                tk.END,
                empty_text,
            )
            return

        for value in values:
            listbox.insert(
                tk.END,
                value,
            )

    def _clear_console(self) -> None:
        if self.selected_id:
            self.console_lines[self.selected_id] = []
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", tk.END)
        self.console_text.configure(state="disabled")

    def _server_state(
        self,
        server: ServerInfo,
    ) -> str:
        if server.id in self.busy:
            return "🟡 Update"

        if self.processes.is_running(server.id):
            return "🟢 Running"

        return "🔴 Stopped"

    def _update_buttons(
        self,
        server: ServerInfo,
    ) -> None:
        running = self.processes.is_running(
            server.id
        )
        busy = server.id in self.busy

        start_script_available = bool(
            server.action_scripts.get("start")
        )

        stop_available = (
            is_minecraft_server(server.server_type)
            or supports_ctrl_break_stop(server.server_type)
            or bool(server.action_scripts.get("stop"))
        )

        restart_available = (
            start_script_available
            and (
                is_minecraft_server(server.server_type)
                or supports_ctrl_break_stop(server.server_type)
                or bool(server.action_scripts.get("stop"))
            )
        )

        update_available = (
            bool(server.action_scripts.get("update"))
            or self.updates.supports_automatic_update(server)
        )

        self.action_buttons["start"].configure(
            state=(
                "disabled"
                if running
                or busy
                or not start_script_available
                else "normal"
            )
        )

        self.action_buttons["stop"].configure(
            state=(
                "normal"
                if running
                and stop_available
                and not busy
                else "disabled"
            )
        )

        self.action_buttons["restart"].configure(
            state=(
                "normal"
                if restart_available
                and not busy
                else "disabled"
            )
        )

        self.action_buttons["update"].configure(
            state=(
                "normal"
                if update_available
                and not running
                and not busy
                else "disabled"
            )
        )

    def _on_server_selected(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        selection = self.server_tree.selection()

        if not selection:
            return

        server = self.manager.get_server(
            selection[0]
        )

        self._display_server(server)

    def _selected_server(
        self,
    ) -> ServerInfo | None:
        if not self.selected_id:
            return None

        return self.manager.get_server(
            self.selected_id
        )

    def _add_server(self) -> None:
        initial_directory = self.settings.server_root
        if not initial_directory.is_dir():
            initial_directory = Path.home()
        folder = filedialog.askdirectory(
            title="Select server folder",
            initialdir=str(initial_directory),
        )

        if not folder:
            return

        try:
            server = self.manager.detect_server(
                folder
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                str(exc),
            )
            return

        confirmed = messagebox.askyesno(
            "Add server",
            (
                f"{self._friendly_server_type(server.server_type)} "
                f"detected.\n\n"
                f"Add {server.name}?"
            ),
        )

        if not confirmed:
            return

        try:
            self.manager.add_server(server)
            self._reload(server.id)

        except Exception as exc:
            messagebox.showerror(
                "Error",
                str(exc),
            )

    def _open_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(True, True)

        outer = ttk.Frame(dialog, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        server_var = tk.StringVar(value=str(self.settings.server_root))
        backup_var = tk.StringVar(value=str(self.settings.backup_root))
        autostart_var = tk.BooleanVar(value=self.settings.task_autostart)
        active_server_var = tk.BooleanVar(value=self.settings.autostart_active_server)
        maintenance_var = tk.BooleanVar(value=self.settings.task_daily_maintenance)
        maintenance_time_var = tk.StringVar(value=self.settings.task_daily_time)
        ntfy_enabled_var = tk.BooleanVar(value=self.settings.ntfy_enabled)
        ntfy_server_var = tk.StringVar(value=self.settings.ntfy_server_url)
        ntfy_topic_var = tk.StringVar(value=self.settings.ntfy_topic)

        ttk.Label(outer, text="Default folders", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(outer, text="Server folder:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=server_var, width=65).grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(outer, text="Browse...", command=lambda: self._choose_settings_folder(server_var, "Select default server folder")).grid(row=1, column=2, pady=4)
        ttk.Label(outer, text="Backup folder:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=backup_var, width=65).grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(outer, text="Browse...", command=lambda: self._choose_settings_folder(backup_var, "Select backup folder")).grid(row=2, column=2, pady=4)

        ttk.Separator(outer).grid(row=3, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(outer, text="Windows startup and maintenance", font=("Segoe UI", 13, "bold")).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Checkbutton(outer, text="Start Game Server Manager at Windows logon", variable=autostart_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(outer, text="Automatically start the active server after manager startup", variable=active_server_var).grid(row=6, column=0, columnspan=3, sticky="w", padx=(22, 0), pady=2)
        ttk.Checkbutton(outer, text="Run daily maintenance for the active server", variable=maintenance_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(outer, text="Time (HH:MM):").grid(row=7, column=1, sticky="e", padx=(0, 86))
        ttk.Entry(outer, textvariable=maintenance_time_var, width=8).grid(row=7, column=2, sticky="w", pady=2)

        ttk.Separator(outer).grid(row=8, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(outer, text="ntfy notifications", font=("Segoe UI", 13, "bold")).grid(row=9, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Checkbutton(outer, text="Send ntfy notifications for application errors and exceptions", variable=ntfy_enabled_var).grid(row=10, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(outer, text="ntfy server:").grid(row=11, column=0, sticky="w", pady=3)
        ttk.Entry(outer, textvariable=ntfy_server_var).grid(row=11, column=1, columnspan=2, sticky="ew", padx=8, pady=3)
        ttk.Label(outer, text="Topic:").grid(row=12, column=0, sticky="w", pady=3)
        ttk.Entry(outer, textvariable=ntfy_topic_var).grid(row=12, column=1, columnspan=2, sticky="ew", padx=8, pady=3)
        ttk.Label(outer, text="No credentials are required. Use a unique topic name and subscribe to it in the ntfy app.", foreground="#555555").grid(row=13, column=0, columnspan=3, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(outer)
        buttons.grid(row=14, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Restore defaults", command=lambda: self._restore_default_folder_values(server_var, backup_var)).pack(side="left")
        ttk.Button(buttons, text="Test ntfy", command=lambda: self._test_ntfy_settings(dialog, ntfy_server_var.get(), ntfy_topic_var.get())).pack(side="left", padx=8)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=lambda: self._save_settings_dialog(dialog, server_var.get(), backup_var.get(), autostart_var.get(), active_server_var.get(), maintenance_var.get(), maintenance_time_var.get(), ntfy_enabled_var.get(), ntfy_server_var.get(), ntfy_topic_var.get())).pack(side="right", padx=(0, 8))

        dialog.update_idletasks()
        dialog.minsize(820, min(620, dialog.winfo_reqheight()))
        dialog.geometry(f"+{self.winfo_rootx() + 100}+{self.winfo_rooty() + 30}")

    def _test_ntfy_settings(self, dialog: tk.Toplevel, server_url: str, topic: str) -> None:
        manager = NotificationManager(NtfySettings(True, server_url.strip(), topic.strip()))

        def worker() -> None:
            try:
                manager.send_test()
            except Exception as exc:
                self.after(0, lambda error=exc: messagebox.showerror("ntfy test failed", str(error), parent=dialog))
            else:
                self.after(0, lambda: messagebox.showinfo("ntfy test sent", "The test notification was sent successfully.", parent=dialog))
        threading.Thread(target=worker, daemon=True).start()

    def _choose_settings_folder(self, variable: tk.StringVar, title: str) -> None:
        current = Path(variable.get().strip()).expanduser()
        initial = current if current.is_dir() else Path.home()
        selected = filedialog.askdirectory(
            parent=self,
            title=title,
            initialdir=str(initial),
        )
        if selected:
            variable.set(selected)

    def _restore_default_folder_values(
        self, server_var: tk.StringVar, backup_var: tk.StringVar
    ) -> None:
        defaults = self.settings_manager.defaults()
        server_var.set(str(defaults.server_root))
        backup_var.set(str(defaults.backup_root))

    def _save_settings_dialog(
        self, dialog: tk.Toplevel, server_value: str, backup_value: str,
        task_autostart: bool, autostart_active_server: bool,
        task_daily_maintenance: bool, task_daily_time: str,
        ntfy_enabled: bool, ntfy_server_url: str, ntfy_topic: str,
    ) -> None:
        if not server_value.strip() or not backup_value.strip():
            messagebox.showerror("Invalid settings", "Both folder paths are required.", parent=dialog)
            return
        try:
            normalized_time = self.task_scheduler.validate_time(task_daily_time)
            if ntfy_enabled and not ntfy_topic.strip():
                raise ValueError("An ntfy topic is required when notifications are enabled.")
            new_settings = AppSettings(
                server_root=Path(server_value.strip()).expanduser(),
                backup_root=Path(backup_value.strip()).expanduser(),
                task_autostart=task_autostart,
                autostart_active_server=autostart_active_server,
                task_daily_maintenance=task_daily_maintenance,
                task_daily_time=normalized_time,
                ntfy_enabled=ntfy_enabled,
                ntfy_server_url=ntfy_server_url.strip() or "https://ntfy.sh",
                ntfy_topic=ntfy_topic.strip(),
            )
            self.settings_manager.save(new_settings)
            scheduler_errors = []
            if self.task_scheduler.supported:
                try:
                    self.task_scheduler.configure_autostart(task_autostart, autostart_active_server)
                except Exception as exc:
                    scheduler_errors.append(f"Windows autostart: {exc}")
                try:
                    self.task_scheduler.configure_daily_maintenance(task_daily_maintenance, normalized_time)
                except Exception as exc:
                    scheduler_errors.append(f"Daily maintenance: {exc}")
            elif task_autostart or task_daily_maintenance:
                scheduler_errors.append("Windows startup integration is only available on Windows.")

            self.settings = self.settings_manager.load()
            self.notifications = NotificationManager(self.settings.ntfy_settings())
            self.backups = BackupManager(self.settings.backup_root)
            self.updates = UpdateManager(self.backups, self.processes)
        except Exception as exc:
            messagebox.showerror("Settings could not be saved", str(exc), parent=dialog)
            return

        dialog.destroy()
        self._refresh_backups()
        if scheduler_errors:
            messagebox.showwarning("Settings saved with a Windows integration warning", "The settings were saved.\n\n" + "\n".join(scheduler_errors), parent=self)
        else:
            messagebox.showinfo("Settings saved", "The settings have been updated. Existing files were not moved.", parent=self)

    def handle_external_command(self, command: str) -> None:
        """Handle commands from Windows Task Scheduler or a second app invocation."""
        if command == "show":
            self.deiconify()
            self.lift()
            self.focus_force()
            return
        if command == "start-active":
            self._start_active_server_automatically()
            return
        if command == "scheduled-maintenance":
            self._run_scheduled_maintenance()

    def _active_server(self) -> ServerInfo | None:
        return next((server for server in self.manager.servers if server.active), None)

    def _select_server_by_id(self, server_id: str) -> None:
        if self.server_tree.exists(server_id):
            self.server_tree.selection_set(server_id)
            self.server_tree.focus(server_id)
            self.server_tree.see(server_id)
            self.selected_id = server_id
            server = self.manager.get_server(server_id)
            if server is not None:
                self._display_server(server)

    def _start_active_server_automatically(self) -> None:
        server = self._active_server()
        if server is None or self.processes.is_running(server.id) or server.id in self.busy:
            return
        self._select_server_by_id(server.id)
        self._show_console()
        self._clear_console()
        try:
            self.processes.start(server)
            self._append_console(server.id, "[TASK] Active server started automatically.")
            self._display_server(server)
        except Exception as exc:
            self._append_console(server.id, f"[TASK ERROR] Automatic start failed: {exc}")
            self._notify_error_async("Automatic server start failed", str(exc))
            messagebox.showerror("Automatic start failed", str(exc))

    def _run_scheduled_maintenance(self) -> None:
        server = self._active_server()
        if server is None:
            messagebox.showwarning("Scheduled maintenance", "No active server is configured.")
            return
        if server.id in self.busy:
            self._append_console(server.id, "[TASK] Scheduled maintenance skipped: server is busy.")
            return
        self._select_server_by_id(server.id)
        self._show_console()
        self._clear_console()
        self.busy.add(server.id)
        self._update_buttons(server)
        threading.Thread(
            target=self._scheduled_maintenance_worker, args=(server,), daemon=True
        ).start()

    def _scheduled_maintenance_worker(self, server: ServerInfo) -> None:
        try:
            self.after(0, lambda: self._append_console(
                server.id, "[TASK] Daily maintenance started."
            ))
            if self.processes.is_running(server.id):
                self.after(0, lambda: self._append_console(
                    server.id, "[TASK] Stopping server safely..."
                ))
                if not self.processes.stop(server):
                    raise RuntimeError("The server could not be stopped safely.")
            self.after(0, lambda: self._append_console(
                server.id, "[TASK] Running server and plugin update..."
            ))
            result = self.updates.update_server(
                server,
                progress_callback=lambda path, current, total: self.after(
                    0, lambda p=path, c=current, t=total: self._append_console(
                        server.id, f"[BACKUP] {c}/{t} {p}"
                    )
                ),
            )
            backup, code, output = result
            if backup is not None:
                self.after(0, lambda: self._append_console(
                    server.id, f"[TASK] Safety backup created: {backup.archive_path}"
                ))
            if output:
                self.after(0, lambda text=output: self._append_console(server.id, text))
            if code != 0:
                raise RuntimeError(f"The update process failed with exit code {code}.")
            self.after(0, lambda: self._append_console(
                server.id, "[TASK] Update completed. Starting server..."
            ))
            self.processes.start(server)
            self.after(0, lambda: self._scheduled_maintenance_finished(server, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._scheduled_maintenance_finished(server, error))

    def _scheduled_maintenance_finished(
        self, server: ServerInfo, error: Exception | None
    ) -> None:
        self.busy.discard(server.id)
        if error is None:
            self._append_console(server.id, "[TASK] Daily maintenance completed successfully.")
        else:
            self._append_console(server.id, f"[TASK ERROR] Daily maintenance failed: {error}")
            self._notify_error_async("Scheduled maintenance failed", str(error))
            messagebox.showerror("Scheduled maintenance failed", str(error))
        self._refresh_backups()
        self._reload(server.id)

    def _show_console(self) -> None:
        """Open the Console tab."""
        self.notebook.select(self.console_tab)

    def _run_action(
        self,
        action: str,
    ) -> None:
        self._show_console()
        server = self._selected_server()

        if server is None:
            return

        # Lifecycle actions start with a clean console view while log files retain history.
        self._clear_console()

        if action == "start":
            self.busy.add(server.id)
            self._update_buttons(server)
            threading.Thread(
                target=self._run_action_worker,
                args=(server, action),
                daemon=True,
            ).start()
            return

        if action == "update":
            automatic_server_update = self.updates.supports_automatic_update(server)
            if automatic_server_update:
                detail = (
                    "The latest stable version of this server type will be downloaded "
                    "and installed directly from the official provider."
                )
                if server.action_scripts.get("update", "").strip():
                    detail += (
                        " The optional update script will then run "
                        "for plugins and other server-specific changes."
                    )
            else:
                detail = "The configured update script will be executed."
            confirmed = messagebox.askyesno(
                "Update",
                f"{detail}\n\nBefore making changes, a "
                "full safety backup will be created.\n\nRun the update now?",
            )
            if not confirmed:
                return

        if action in {"stop", "restart"}:
            confirmed = messagebox.askyesno(
                ACTION_LABELS[action],
                (
                    f"{server.name}: "
                    f"Run {ACTION_LABELS[action]}?"
                ),
            )

            if not confirmed:
                return

        self.busy.add(server.id)
        self._update_buttons(server)

        worker = threading.Thread(
            target=self._run_action_worker,
            args=(server, action),
            daemon=True,
        )
        worker.start()

    def _run_action_worker(
        self,
        server: ServerInfo,
        action: str,
    ) -> None:
        try:
            if action == "start":
                result = self.processes.start(server)

            elif action == "stop":
                result = self.processes.stop(server)

            elif action == "restart":
                result = self.processes.restart(server)

            elif action == "update":
                result = self.updates.update_server(
                    server,
                    progress_callback=lambda path, current, total: self.after(
                        0,
                        lambda p=path, c=current, t=total: self._append_console(
                            server.id, f"[BACKUP] {c}/{t} {p}"
                        ),
                    ),
                )

            else:
                raise RuntimeError(
                    f"Unknown action: {action}"
                )

            self.after(
                0,
                lambda completed_server=server,
                completed_action=action,
                completed_result=result: self._action_finished(
                    completed_server,
                    completed_action,
                    completed_result,
                    None,
                ),
            )

        except Exception as exc:
            self.after(
                0,
                lambda completed_server=server,
                completed_action=action,
                error=exc: self._action_finished(
                    completed_server,
                    completed_action,
                    None,
                    error,
                ),
            )

    def _action_finished(
        self,
        server: ServerInfo,
        action: str,
        result: object,
        error: Exception | None,
    ) -> None:
        self.busy.discard(server.id)

        if error is not None:
            messagebox.showerror(
                "Action failed",
                str(error),
            )

        elif action == "stop" and result is False:
            force_stop = messagebox.askyesno(
                "No response",
                (
                    "The server did not stop within the timeout.\n\n"
                    "Force-terminate the process?"
                ),
            )

            if force_stop:
                self.processes.force_stop(
                    server.id
                )

        elif action == "update":
            backup, code, output = result
            if backup is not None:
                self._append_console(
                    server.id,
                    f"[BACKUP] Safety backup created: {backup.archive_path}",
                )

            if output:
                formatted_output = (
                    "[UPDATE] "
                    + output.replace(
                        "\n",
                        "\n[UPDATE] ",
                    )
                )

                self._append_console(
                    server.id,
                    formatted_output,
                )

            if code == 0:
                messagebox.showinfo(
                    "Update",
                    "Update completed.",
                )
            else:
                messagebox.showerror(
                    "Update",
                    f"Error code {code}",
                )

        self._reload(server.id)

    def _choose_script(self, action: str) -> None:
        server = self._selected_server()
        if server is None:
            return

        selected_file = filedialog.askopenfilename(
            initialdir=server.path,
            title=f"{ACTION_LABELS[action]} script",
            filetypes=[
                ("Executable scripts", "*.bat *.cmd *.ps1 *.exe"),
                ("All files", "*.*"),
            ],
        )
        if not selected_file:
            return

        scripts = {name: self.script_vars[name].get() for name in SCRIPT_ACTIONS}
        scripts[action] = selected_file
        try:
            saved = self.manager.save_scripts(server.id, scripts)
            self.script_vars[action].set(saved.action_scripts.get(action, ""))
            self._reload(server.id)
        except Exception as exc:
            messagebox.showerror("Script selection failed", str(exc))

    def _clear_script(self, action: str) -> None:
        server = self._selected_server()
        if server is None:
            return
        scripts = {name: self.script_vars[name].get() for name in SCRIPT_ACTIONS}
        scripts[action] = ""
        try:
            self.manager.save_scripts(server.id, scripts)
            self._reload(server.id)
        except Exception as exc:
            messagebox.showerror("Script selection failed", str(exc))

    def _open_backup_selection(self) -> None:
        server = self._selected_server()
        if server is None or is_minecraft_server(server.server_type):
            return

        dialog = tk.Toplevel(self)
        dialog.title("Select backup files and folders")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("720x430")
        dialog.minsize(600, 360)

        ttk.Label(
            dialog,
            text=(
                "Choose files and folders inside the server directory. Multiple files "
                "can be selected in one dialog. Folders can be added one after another."
            ),
            wraplength=670,
            padding=(12, 12, 12, 6),
        ).pack(fill="x")

        list_frame = ttk.Frame(dialog, padding=(12, 6))
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        selection_list = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=("Consolas", 9),
            yscrollcommand=scrollbar.set,
        )
        selection_list.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=selection_list.yview)
        for value in server.backup_paths:
            selection_list.insert(tk.END, value)

        def add_values(paths: tuple[str, ...] | list[str]) -> None:
            current = set(selection_list.get(0, tk.END))
            root = Path(server.path).resolve()
            for raw in paths:
                path = Path(raw).resolve()
                try:
                    relative = path.relative_to(root).as_posix()
                except ValueError:
                    messagebox.showerror(
                        "Invalid backup path",
                        "Backup items must be located inside the server folder.",
                        parent=dialog,
                    )
                    continue
                if relative not in current:
                    selection_list.insert(tk.END, relative)
                    current.add(relative)

        def add_files() -> None:
            selected = filedialog.askopenfilenames(
                parent=dialog,
                initialdir=server.path,
                title="Select backup files",
                filetypes=[("All files", "*.*")],
            )
            add_values(selected)

        def add_folder() -> None:
            selected = filedialog.askdirectory(
                parent=dialog,
                initialdir=server.path,
                title="Select backup folder",
                mustexist=True,
            )
            if selected:
                add_values([selected])

        def remove_selected() -> None:
            for index in reversed(selection_list.curselection()):
                selection_list.delete(index)

        def save_selection() -> None:
            try:
                self.manager.save_backup_paths(
                    server.id,
                    list(selection_list.get(0, tk.END)),
                )
                dialog.destroy()
                self._reload(server.id)
            except Exception as exc:
                messagebox.showerror("Backup selection failed", str(exc), parent=dialog)

        toolbar = ttk.Frame(dialog, padding=(12, 0, 12, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Add files...", command=add_files).pack(side="left")
        ttk.Button(toolbar, text="Add folder...", command=add_folder).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Remove selected", command=remove_selected).pack(side="left")
        ttk.Button(toolbar, text="Clear", command=lambda: selection_list.delete(0, tk.END)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(toolbar, text="Use selection", command=save_selection).pack(side="right", padx=6)

        dialog.wait_window()

    def _refresh_server(self) -> None:
        server = self._selected_server()

        if server is None:
            return

        try:
            self.manager.refresh_server(
                server.id
            )
            self._reload(server.id)

        except Exception as exc:
            messagebox.showerror(
                "Error",
                str(exc),
            )

    def _set_active_server(self) -> None:
        server = self._selected_server()

        if server is None:
            return

        self.manager.set_active_server(
            server.id
        )
        self._reload(server.id)

    def _remove_server(self) -> None:
        server = self._selected_server()

        if server is None:
            return

        if self.processes.is_running(server.id):
            messagebox.showwarning(
                "Server is running",
                (
                    "A running server cannot be "
                    "removed from the manager."
                ),
            )
            return

        confirmed = messagebox.askyesno(
            "Remove server",
            (
                f"Remove {server.name} from Game Server Manager?\n\n"
                "This only removes the server entry from the manager. "
                "The server files, worlds, and backups will remain on disk."
            ),
        )

        if not confirmed:
            return

        self.manager.remove_server(
            server.id
        )
        self.selected_id = None
        self._reload()

    def _open_server_folder(self) -> None:
        server = self._selected_server()

        if server is not None:
            os.startfile(server.path)


    def _queue_output(
        self,
        server_id: str,
        text: str,
    ) -> None:
        self.after(
            0,
            lambda queued_server_id=server_id,
            queued_text=text: self._append_console(
                queued_server_id,
                queued_text,
            ),
        )

    def _queue_exit(
        self,
        server_id: str,
        return_code: int,
    ) -> None:
        self.after(
            0,
            lambda queued_server_id=server_id,
            queued_return_code=return_code: self._process_exited(
                queued_server_id,
                queued_return_code,
            ),
        )

    def _process_exited(
        self,
        server_id: str,
        return_code: int,
    ) -> None:
        self._reload(server_id)

        if return_code == 0:
            return

        server = self.manager.get_server(
            server_id
        )

        server_name = (
            server.name
            if server is not None
            else "Server"
        )

        self._notify_error_async(
            f"{server_name} process exited unexpectedly",
            f"The server process exited with error code {return_code}. See the integrated console and log folder for details.",
        )

        messagebox.showwarning(
            "Server process exited",
            (
                f"{server_name} exited with error code "
                f"{return_code}.\n\n"
                "More details are available in the "
                "Console tab and the log folder."
            ),
        )

    def _append_console(
        self,
        server_id: str,
        text: str,
    ) -> None:
        lines = self.console_lines.setdefault(
            server_id,
            [],
        )

        lines.extend(
            str(text).splitlines()
        )

        if len(lines) > self.console_line_limit:
            del lines[:-self.console_line_limit]

        self._parse_player_status(server_id, str(text))

        if server_id != self.selected_id:
            return

        self.console_text.configure(
            state="normal"
        )
        self.console_text.insert(
            tk.END,
            f"{text}\n",
        )
        self.console_text.see(tk.END)
        self.console_text.configure(
            state="disabled"
        )

    def _parse_player_status(self, server_id: str, text: str) -> None:
        # Covers current Vanilla/Paper-family list command formats.
        match = re.search(
            r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online:\s*(.*)",
            text, re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online",
                text, re.IGNORECASE,
            )
        if not match:
            return
        current = int(match.group(1))
        maximum = int(match.group(2))
        tail = match.group(3).strip() if match.lastindex and match.lastindex >= 3 else ""
        names = [name.strip() for name in tail.split(",") if name.strip()]
        self.player_status[server_id] = (current, maximum, names)

    def _update_live_status(self, server: ServerInfo) -> None:
        if not hasattr(self, "live_players_var"):
            return
        running = self.processes.is_running(server.id)
        if is_minecraft_server(server.server_type):
            player_data = self.player_status.get(server.id)
            if player_data:
                current, maximum, names = player_data
                maximum_text = str(maximum) if maximum is not None else "?"
                self.live_players_var.set(f"Players: {current} / {maximum_text}")
                self.live_names_var.set(
                    "Player names: " + (", ".join(names) if names else "none")
                )
            elif running:
                self.live_players_var.set("Players: waiting for server response...")
                self.live_names_var.set("Player names: waiting for server response...")
            else:
                self.live_players_var.set("Players: 0 (server stopped)")
                self.live_names_var.set("Player names: none")
        else:
            self.live_players_var.set("Players: not available for this server type")
            self.live_names_var.set("Player names: not available for this server type")

        if psutil is None:
            self.live_server_resource_var.set(
                "Server process: live CPU/RAM metrics require the optional psutil package"
            )
            self.live_system_resource_var.set(
                "System: live CPU/RAM metrics require the optional psutil package"
            )
            return
        try:
            vm = psutil.virtual_memory()
            self.live_system_resource_var.set(
                f"System: CPU {psutil.cpu_percent(interval=None):.1f}% | "
                f"RAM {vm.percent:.1f}% ({format_size(vm.used)} / {format_size(vm.total)})"
            )
            pid = self.processes.get_process_id(server.id)
            if pid is None:
                self.live_server_resource_var.set("Server process: stopped")
                return
            parent = psutil.Process(pid)
            processes = [parent] + parent.children(recursive=True)
            cpu = sum(p.cpu_percent(interval=None) for p in processes if p.is_running())
            memory = sum(p.memory_info().rss for p in processes if p.is_running())
            self.live_server_resource_var.set(
                f"Server process tree: CPU {cpu:.1f}% | RAM {format_size(memory)} | PID {pid}"
            )
        except (psutil.Error, OSError):
            self.live_server_resource_var.set("Server process: metrics temporarily unavailable")

    def _query_minecraft_players(self, server: ServerInfo) -> None:
        if not is_minecraft_server(server.server_type):
            return
        if not self.processes.is_running(server.id):
            return
        now = time.monotonic()
        if now - self.last_player_query.get(server.id, 0.0) < 15.0:
            return
        self.last_player_query[server.id] = now
        try:
            self.processes.send_command(server.id, "list")
        except RuntimeError:
            pass

    def _poll(self) -> None:
        for server in self.manager.servers:
            if self.server_tree.exists(server.id):
                self.server_tree.set(
                    server.id,
                    "state",
                    self._server_state(server),
                )

        server = self._selected_server()

        if server is not None:
            self.server_status_var.set(self._server_state(server))
            self._update_buttons(server)
            running = self.processes.is_running(server.id)
            self._set_console_input_state(running)
            self._query_minecraft_players(server)
            self._update_live_status(server)
        else:
            self._set_console_input_state(False)
            self.live_players_var.set("Players: no server selected")
            self.live_names_var.set("Player names: none")
            self.live_server_resource_var.set("Server process: unavailable")
            if psutil is None:
                self.live_system_resource_var.set(
                    "System: live CPU/RAM metrics require the optional psutil package"
                )
            else:
                try:
                    vm = psutil.virtual_memory()
                    self.live_system_resource_var.set(
                        f"System: CPU {psutil.cpu_percent(interval=None):.1f}% | "
                        f"RAM {vm.percent:.1f}% ({format_size(vm.used)} / {format_size(vm.total)})"
                    )
                except (psutil.Error, OSError):
                    self.live_system_resource_var.set(
                        "System: metrics temporarily unavailable"
                    )

        self.after(
            1000,
            self._poll,
        )

    @staticmethod
    def _friendly_server_type(
        server_type: str,
    ) -> str:
        return get_server_type_name(server_type)

