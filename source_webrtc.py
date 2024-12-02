import asyncio
import json
import sys
import base64
import av
import logging

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack

# Configure logging to write to stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

pcs = set()

async def index(request):
    return web.FileResponse('./source_webrtc.html')

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("track")
    async def on_track(track):
        if track.kind == "audio":
            logger.info(f"Received audio track")
            asyncio.create_task(handle_audio_track(track))
        elif track.kind == "video":
            logger.info(f"Received video track")
            asyncio.create_task(handle_video_track(track))

    async def handle_audio_track(track):
        resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=24000
        )
        while True:
            try:
                frame = await track.recv()
                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    audio_data = resampled_frame.to_ndarray().tobytes()
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    message = {
                        "type": "pcmux.audio.delta",
                        "delta": audio_base64
                    }
                    # PCMux output goes to stdout
                    print(json.dumps(message), flush=True, file=sys.stdout)
            except Exception as e:
                logger.error(f"Error processing audio track: {e}")
                break

    async def handle_video_track(track):
        resampler = av.video.resampler.VideoResampler(format='rgb24')
        while True:
            try:
                frame = await track.recv()
                resampled_frame = resampler.resample(frame)
                video_data = resampled_frame.to_ndarray().tobytes()
                video_base64 = base64.b64encode(video_data).decode('utf-8')
                message = {
                    "type": "pcmux.video.delta",
                    "delta": video_base64
                }
                print(json.dumps(message), flush=True, file=sys.stdout)
            except Exception as e:
                logger.error(f"Error processing video track: {e}")
                break

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # Handle the offer
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Send back the answer
    response = {
        'sdp': pc.localDescription.sdp,
        'type': pc.localDescription.type
    }
    return web.Response(
        content_type='application/json',
        text=json.dumps(response)
    )

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

def main():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_post('/offer', offer)
    app.on_shutdown.append(on_shutdown)
    logger.info("Starting WebRTC server on port 8080")
    web.run_app(app, port=8080, print=lambda *args: logger.info(*args))

if __name__ == '__main__':
    main()
