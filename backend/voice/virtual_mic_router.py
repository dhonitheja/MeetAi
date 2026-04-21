import numpy as np
import sounddevice as sd
import platform
import asyncio

class VirtualMicRouter:
    """
    Routes generated audio chunks to a virtual microphone device.
    Handles the float32 -> int16 conversion at the hardware boundary.
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.os = platform.system()
        self.target_device_name = self._get_default_target_name()
        self.device_index = self._find_device_index()
        
    def _get_default_target_name(self) -> str:
        if self.os == "Windows":
            return "CABLE Input" # VB-Audio Cable
        elif self.os == "Darwin":
            return "BlackHole 2ch"
        return ""

    def _find_device_index(self) -> int:
        """Searches for the virtual mic device index."""
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if self.target_device_name in dev['name']:
                # We want the Input side of the virtual cable (which acts as a speaker to us)
                if dev['max_output_channels'] > 0:
                    return i
        
        print(f"[VirtualMicRouter] WARNING: '{self.target_device_name}' not found. Using system default output.")
        return sd.default.device[1] # Default output

    def _convert_to_int16(self, chunk: np.ndarray) -> np.ndarray:
        """
        Converts float32 audio (-1.0 to 1.0) to int16 for the soundcard.
        Prevents crackling by clamping before scaling.
        """
        # Clamp to [-1.0, 1.0]
        clamped = np.clip(chunk, -1.0, 1.0)
        # Scale to int16 range
        return (clamped * 32767).astype(np.int16)

    async def route_audio_stream(self, audio_generator):
        """
        Consumes an async generator of float32 chunks and writes them to the virtual mic.
        """
        print(f"[VirtualMicRouter] Starting stream to device {self.device_index}...")
        
        try:
            # We open an output stream on the virtual mic
            # Note: sounddevice can handle float32 if the hardware does, 
            # but we convert to int16 for maximum compatibility with virtual drivers.
            with sd.OutputStream(
                device=self.device_index,
                channels=1,
                samplerate=self.sample_rate,
                dtype='int16'
            ) as stream:
                async for float_chunk in audio_generator:
                    int_chunk = self._convert_to_int16(float_chunk)
                    
                    # Handle multi-dimensional chunks if necessary
                    if len(int_chunk.shape) == 1:
                        int_chunk = int_chunk.reshape(-1, 1)
                        
                    # Write to the soundcard buffer
                    stream.write(int_chunk)
                    
        except Exception as e:
            print(f"[VirtualMicRouter] Stream error: {e}")

# ─── Usage Example ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    router = VirtualMicRouter()
    print(f"OS: {router.os}, Device: {router.target_device_name} (Index: {router.device_index})")
