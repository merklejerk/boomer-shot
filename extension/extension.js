import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export default class BoomerShotExtension extends Extension {
    enable() {
        this._settings = this.getSettings();

        // Register hotkey for area screenshot (Super+Shift+S by default)
        Main.wm.addKeybinding(
            'snip-area',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL,
            () => this._triggerCapture('area')
        );

        // Register hotkey for window screenshot (Super+Shift+W by default)
        Main.wm.addKeybinding(
            'snip-window',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL,
            () => this._triggerCapture('window')
        );
    }

    disable() {
        Main.wm.removeKeybinding('snip-area');
        Main.wm.removeKeybinding('snip-window');
        this._settings = null;
    }

    _triggerCapture(mode) {
        const shooter = new Shell.Screenshot();
        const tmpDir = GLib.get_tmp_dir();
        const filename = `${tmpDir}/boomer_shot_${mode}_raw.png`;

        if (mode === 'area') {
            // Get monitor containing the mouse pointer
            const [x, y] = global.get_pointer();
            const monitor = Main.layoutManager.monitors.find(
                m => x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height
            ) || Main.layoutManager.primaryMonitor;

            // In GNOME 50, screenshot_area expects a Gio.OutputStream instead of a filename string
            const file = Gio.File.new_for_path(filename);
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);

            shooter.screenshot_area(
                monitor.x,
                monitor.y,
                monitor.width,
                monitor.height,
                stream,
                (obj, res) => {
                    let success = false;
                    try {
                        const [ok, rect] = shooter.screenshot_area_finish(res);
                        success = ok;
                    } catch (e) {
                        console.error('[BoomerShot] Failed to capture monitor area:', e);
                    } finally {
                        try {
                            stream.close(null);
                        } catch (err) {
                            console.error('[BoomerShot] Failed to close stream:', err);
                        }
                    }

                    if (success) {
                        this._launchEditor('area', filename);
                    } else {
                        console.error('[BoomerShot] Capture was unsuccessful');
                    }
                }
            );
        } else if (mode === 'window') {
            // Capture focused window
            const includeFrame = true;
            const includeCursor = false;

            // In GNOME 50, screenshot_window expects (include_frame, include_cursor, stream, callback)
            const file = Gio.File.new_for_path(filename);
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);

            shooter.screenshot_window(
                includeFrame,
                includeCursor,
                stream,
                (obj, res) => {
                    let success = false;
                    try {
                        const [ok, rect] = shooter.screenshot_window_finish(res);
                        success = ok;
                    } catch (e) {
                        console.error('[BoomerShot] Failed to capture window:', e);
                    } finally {
                        try {
                            stream.close(null);
                        } catch (err) {
                            console.error('[BoomerShot] Failed to close stream:', err);
                        }
                    }

                    if (success) {
                        this._launchEditor('window', filename);
                    } else {
                        console.error('[BoomerShot] Window capture was unsuccessful');
                    }
                }
            );
        }
    }

    _launchEditor(mode, filename) {
        const scriptPath = `${this.path}/src/main.py`;

        try {
            Gio.Subprocess.new(
                ['python3', scriptPath, '--mode', mode, '--file', filename],
                Gio.SubprocessFlags.NONE
            );
        } catch (e) {
            console.error('[BoomerShot] Failed to spawn python editor:', e);
        }
    }
}
