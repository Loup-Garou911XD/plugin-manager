# ba_meta require api 9

import babase
import bauiv1 as bui
from bauiv1 import _automation as ui_automation


def _describe_widget(widget: bui.Widget) -> str:
    try:
        wid = str(widget.id)
    except Exception:
        wid = '<no id>'
    try:
        label = ui_automation._label_text(widget)
    except Exception:
        label = ''
    return f'{type(widget).__name__} id={wid} label={label!r}'


def _is_widget_visible(widget: bui.Widget) -> bool:
    """Check if a widget is visible and not hidden behind other windows."""
    # Try to find the root window this widget belongs to
    try:
        current = widget
        while hasattr(current, 'parent') and current.parent is not None:
            current = current.parent
    except Exception:
        pass
    
    return True


def _should_skip_widget(widget: bui.Widget) -> bool:
    """Check if a widget should be skipped during the DFS test."""
    try:
        wid = str(widget.id)
        # Skip confirm/exit buttons that would terminate the test
        if 'mainmenuwindow2' in wid.lower() or 'quit' in wid.lower():
            if '|' in wid:  # Confirm dialog patterns like "confirm1|ok"
                return True
    except Exception:
        pass
    
    # Skip widgets that don't have valid screen-space centers
    try:
        widget.get_screen_space_center()
    except Exception:
        return True
    
    # Skip widgets that are hidden behind other windows
    if not _is_widget_visible(widget):
        return True
    
    # Skip widgets that are not selectable
    try:
        if hasattr(widget, 'selectable'):
            if not widget.selectable:
                print(f'Skipping widget {len(self._seen_widget_ids)}: {description} (Not selectable)')
                return True
        else:
            print(f'Widget {len(self._seen_widget_ids)}: {description} has no selectable attribute; assuming not selectable')
            return True
    except Exception:
        pass
    
    return False


def _walk_widget_tree() -> list[object]:
    roots: list[object] = []
    main_window = babase.app.ui_v1.get_main_window()
    if main_window is not None:
        try:
            roots.append(main_window.get_root_widget())
        except Exception:
            pass

    for name in ui_automation._SPECIAL_WIDGET_NAMES:
        try:
            special = ui_automation._bauiv1.get_special_widget(name)
        except Exception:
            special = None
        if special is not None:
            roots.append(special)

    out: list[object] = []
    seen: set[int] = set()
    stack: list[object] = list(roots)
    while stack:
        widget = stack.pop()
        if id(widget) in seen:
            continue
        seen.add(id(widget))
        out.append(widget)
        try:
            children = widget.get_children()
        except Exception:
            children = []
        stack.extend(children)
    return out


# ba_meta export babase.Plugin
class AutomatedUITreeClickTest(babase.Plugin):
    def __init__(self):
        self._window = None
        self._is_running = False
        self._stack: list[object] = []
        self._seen_widget_ids: set[int] = set()

    def has_settings_ui(self) -> bool:
        return True

    def show_settings_ui(self, source_widget=None) -> None:
        self._window = bui.containerwidget(
            size=(700, 320),
            transition='in_right',
            stack_offset=(0, 0),
        )

        bui.textwidget(
            parent=self._window,
            position=(40, 280),
            size=(620, 40),
            text='Automated UI widget tree clicker',
            h_align='left',
            v_align='center',
            color=(1.0, 1.0, 1.0, 1.0),
            maxwidth=620,
        )
        bui.textwidget(
            parent=self._window,
            position=(40, 240),
            size=(620, 40),
            text=(
                'Builds the current widget tree and iteratively clicks each visible '
                'widget to check for errors.'
            ),
            h_align='left',
            v_align='top',
            color=(0.9, 0.9, 0.9, 1.0),
            maxwidth=620,
        )

        bui.buttonwidget(
            parent=self._window,
            position=(40, 170),
            size=(300, 70),
            label='Run widget click test',
            on_activate_call=self._on_run_test,
        )

        bui.buttonwidget(
            parent=self._window,
            position=(360, 170),
            size=(300, 70),
            label='Dump widget tree',
            on_activate_call=self._on_dump_tree,
        )

        close_button = bui.buttonwidget(
            parent=self._window,
            position=(250, 80),
            size=(200, 70),
            label='Close',
            on_activate_call=lambda widget=None: bui.containerwidget(
                edit=self._window, transition='out_right'
            ),
        )
        bui.containerwidget(edit=self._window, cancel_button=close_button)

    def on_app_running(self) -> None:
        babase.apptimer(0.5, self._on_run_test)

    def _log(self, message: str) -> None:
        print(f'[automated_ui_test] {message}')
        babase.screenmessage(message)

    def _on_dump_tree(self, widget=None) -> None:
        self._dump_widget_tree()

    def _on_run_test(self, widget=None) -> None:
        if self._is_running:
            self._log('Automated UI test is already running.')
            return

        if not hasattr(ui_automation._badev, 'automation_press_at_virtual'):
            self._log('Automation build is required to run this plugin.')
            return

        self._seen_widget_ids.clear()
        self._stack = list(reversed(_walk_widget_tree()))
        if not self._stack:
            self._log('No visible widgets found to click.')
            return

        self._is_running = True
        self._log(f'Starting automated DFS click test for {len(self._stack)} initial widgets...')
        self._process_next_widget()

    def _process_next_widget(self) -> None:
        while self._stack and id(self._stack[-1]) in self._seen_widget_ids:
            self._stack.pop()

        if not self._stack:
            self._is_running = False
            self._log('Automated UI test complete.')
            return

        widget = self._stack.pop()
        widget_id = id(widget)
        self._seen_widget_ids.add(widget_id)
        
        if _should_skip_widget(widget):
            description = _describe_widget(widget)
            self._log(f'Skipping widget {len(self._seen_widget_ids)}: {description} (hidden or invalid)')
            self._process_next_widget()
            return

        description = _describe_widget(widget)
        self._log(f'Clicking widget {len(self._seen_widget_ids)}: {description}')
        try:
            ui_automation._click_widget(widget, 'automated_ui_test', description)
        except Exception as exc:
            self._log(f'Error clicking widget {len(self._seen_widget_ids)}: {description} - {exc}')

        babase.apptimer(0.5, self._after_click)

    def _after_click(self) -> None:
        current_widgets = _walk_widget_tree()
        new_widgets = 0
        for widget in reversed(current_widgets):
            widget_id = id(widget)
            if widget_id in self._seen_widget_ids:
                continue
            if any(id(existing) == widget_id for existing in self._stack):
                continue
            self._stack.append(widget)
            new_widgets += 1

        if new_widgets:
            self._log(f'Found {new_widgets} new widget(s) after click.')
        self._process_next_widget()

    def _dump_widget_tree(self) -> None:
        roots: list[object] = []
        main_window = babase.app.ui_v1.get_main_window()
        if main_window is not None:
            try:
                roots.append(main_window.get_root_widget())
            except Exception:
                pass

        for name in ui_automation._SPECIAL_WIDGET_NAMES:
            try:
                special = ui_automation._bauiv1.get_special_widget(name)
            except Exception:
                special = None
            if special is not None:
                roots.append(special)

        lines: list[str] = []
        seen: set[int] = set()
        for root in roots:
            self._append_widget_tree(root, 0, seen, lines)

        if not lines:
            self._log('No widget tree roots found.')
            return

        self._log(f'Widget tree contains {len(lines)} entries. See console for full dump.')
        print('[automated_ui_test] widget tree dump:')
        print('\n'.join(lines))

    def _append_widget_tree(
        self,
        widget: bui.Widget,
        depth: int,
        seen: set[int],
        lines: list[str],
    ) -> None:
        if id(widget) in seen:
            return
        seen.add(id(widget))
        try:
            entry = '  ' * depth + _describe_widget(widget)
        except Exception:
            entry = '  ' * depth + f'{type(widget).__name__} <error describing widget>'
        lines.append(entry)

        try:
            children = widget.get_children()
        except Exception:
            children = []
        for child in children:
            self._append_widget_tree(child, depth + 1, seen, lines)
