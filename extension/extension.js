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

            shooter.screenshot_area(
                monitor.x,
                monitor.y,
                monitor.width,
                monitor.height,
                filename,
                (obj, res) => {
                    try {
                        const [success, filenameUsed] = shooter.screenshot_area_finish(res);
                        if (success) {
                            this._launchEditor('area', filenameUsed);
                        } else {
                            console.error('[BoomerShot] Capture was unsuccessful');
                        }
                    } catch (e) {
                        console.error('[BoomerShot] Failed to capture monitor area:', e);
                    }
                }
            );
        } else if (mode === 'window') {
            // Capture focused window
            const includeFrame = true;
            const includeCursor = false;
            const flash = false;

            shooter.screenshot_window(
                includeFrame,
                includeCursor,
                flash,
                filename,
                (obj, res) => {
                    try {
                        const [success, filenameUsed] = shooter.screenshot_window_finish(res);
                        if (success) {
                            this._launchEditor('window', filenameUsed);
                        } else {
                            console.error('[BoomerShot] Window capture was unsuccessful');
                        }
                    } catch (e) {
                        console.error('[BoomerShot] Failed to capture window:', e);
                    }
                }
            );
        }
    }

    _launchEditor(mode, filename) {
        // Look for the Python editor script in the workspace directory first (dev),
        // and fall back to the installed extension directory (production).
        const workspacePath = '/home/cluracan/code/boomer-shot';
        let scriptPath = `${workspacePath}/src/main.py`;
        
        const file = Gio.File.new_for_path(scriptPath);
        if (!file.query_exists(null)) {
            scriptPath = `${this.path}/src/main.py`;
        }

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
