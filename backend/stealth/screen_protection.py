import ctypes
import platform
import logging

logger = logging.getLogger(__name__)

WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 v2004 (build 19041+) required


class ScreenProtection:
    """
    Applies OS-level screen capture exclusion to a window handle.
    Windows: SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
    macOS:   NSWindow.setSharingType_(NSWindowSharingNone)
    Linux:   No-op - logs warning, does not crash.
    """

    def apply(self, hwnd: int) -> bool:
        """Apply capture exclusion. Returns True if successfully applied."""
        os_name = platform.system()
        if os_name == "Windows":
            return self._apply_windows(hwnd)
        elif os_name == "Darwin":
            return self._apply_macos(hwnd)
        else:
            logger.warning(
                "Screen capture exclusion not supported on Linux. "
                "Overlay may be visible in screen recordings."
            )
            return False

    def _apply_windows(self, hwnd: int) -> bool:
        try:
            user32 = ctypes.windll.user32
            result = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if result:
                logger.info("Screen protection applied (Windows) hwnd=%d", hwnd)
            else:
                logger.error(f"SetWindowDisplayAffinity failed. Code: {ctypes.get_last_error()}")
            return bool(result)
        except Exception as e:
            logger.error(f"Windows screen protection failed: {e}")
            return False

    def _apply_macos(self, hwnd: int) -> bool:
        try:
            import objc
            from AppKit import NSWindowSharingNone

            ns_view = objc.objc_object(c_void_p=ctypes.c_void_p(hwnd))
            ns_window = ns_view.window()
            ns_window.setSharingType_(NSWindowSharingNone)
            logger.info("Screen protection applied (macOS)")
            return True
        except ImportError:
            logger.error("PyObjC not installed. Run: pip install pyobjc-framework-Cocoa")
            return False
        except Exception as e:
            logger.error(f"macOS screen protection failed: {e}")
            return False

    def verify(self, hwnd: int) -> bool:
        """Verify exclusion is active. Windows only - always True on other OS."""
        if platform.system() != "Windows":
            return True
        try:
            affinity = ctypes.c_uint32(0)
            ctypes.windll.user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity))
            return affinity.value == WDA_EXCLUDEFROMCAPTURE
        except Exception:
            return False
