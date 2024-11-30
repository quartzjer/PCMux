#!/usr/bin/env python3

import asyncio
import json
import uuid
import av
import base64
import sys

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack

SERVER_PORT = 8080
WHIP_ENDPOINT = "/whip"

# Add global connection tracking
pcs = set()
pcs_by_resource_id = {}
handlers_by_resource_id = {}

def log(msg):
    """Log to stderr"""
    print(msg, file=sys.stderr, flush=True)

class WHIPHandler:
    def __init__(self, offer: RTCSessionDescription):
        self.pc = RTCPeerConnection()
        self.pc.addTransceiver("audio", direction="recvonly")
        self.pc.addTransceiver("video", direction="recvonly")
        self.offer = offer
        self.id = uuid.uuid4()
        self.connection_closed = asyncio.Event()
        self.video_frame_count = 0

        log(f"Initialized WHIPHandler with ID: {self.id}")

    async def handle_audio_track(self, track: MediaStreamTrack):
        log(f"Handling audio track: {track.kind}")

        resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=24000
        )

        while not self.connection_closed.is_set():
            try:
                frame = await track.recv()
                
                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    audio_data = resampled_frame.to_ndarray().tobytes()
                    # Convert to PCMux format and write to stdout
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    message = {
                        "type": "pcmux.audio.delta",
                        "delta": audio_base64
                    }
                    print(json.dumps(message), flush=True)

            except Exception as e:
                log(f"Error receiving audio frame: {e}")
                self.connection_closed.set()
                break

    async def handle_video_track(self, track: MediaStreamTrack):
        log(f"Handling video track: {track.kind}")
        
        while not self.connection_closed.is_set():
            try:
                frame = await track.recv()
                self.video_frame_count += 1
                if self.video_frame_count % 30 == 0:
                    log(f"Received {self.video_frame_count} video frames")
            except Exception as e:
                log(f"Error receiving video frame: {e}")
                self.connection_closed.set()
                break

    async def _wait_for_ice_gathering(self):
        while self.pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)

    async def run(self):
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            log(f"Connection state changed to: {self.pc.connectionState}")
            if self.pc.connectionState in ["failed", "closed"]:
                self.connection_closed.set()

        @self.pc.on("track")
        async def on_track(track):
            if track.kind == "audio":
                log(f"Received audio track")
                asyncio.create_task(self.handle_audio_track(track))
            elif track.kind == "video":
                log(f"Received video track")
                asyncio.create_task(self.handle_video_track(track))

        await self.pc.setRemoteDescription(self.offer)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        await self._wait_for_ice_gathering()

    async def close(self):
        await self.pc.close()
        pcs.discard(self.pc)
        pcs_by_resource_id.pop(str(self.id), None)
        handlers_by_resource_id.pop(str(self.id), None)
        log(f"WHIPHandler {self.id} closed.")

async def handle_whip(request):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        response.headers.update({
            'Access-Control-Allow-Methods': 'OPTIONS, POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400',
            'Access-Control-Allow-Origin': '*'
        })
        return response

    if request.method != "POST":
        return web.Response(status=405, text="Method Not Allowed")

    try:
        content_type = request.headers.get('Content-Type', '').lower()
        if content_type == 'application/sdp':
            sdp_content = await request.text()
            offer_json = {
                "type": "offer",
                "sdp": sdp_content
            }
        elif content_type == 'application/json':
            offer_json = await request.json()
        else:
            return web.Response(
                status=415,
                text=f"Unsupported Content-Type: {content_type}. Expected application/sdp or application/json"
            )

        log(f"Processed offer: {offer_json}")
    except Exception as e:
        log(f"Error processing request: {e}")
        return web.Response(status=400, text=str(e))

    handler = None
    try:
        offer = RTCSessionDescription(sdp=offer_json.get("sdp"), type=offer_json.get("type", "offer"))
        handler = WHIPHandler(offer)
        resource_id = str(handler.id)
        
        # Track connections
        pcs.add(handler.pc)
        pcs_by_resource_id[resource_id] = handler.pc
        handlers_by_resource_id[resource_id] = handler

        await handler.run()

        answer_sdp = handler.pc.localDescription.sdp
        
        response = web.Response(
            content_type='application/sdp',
            text=answer_sdp,
            status=201
        )
        response.headers.update({
            'Location': f'{WHIP_ENDPOINT}/{resource_id}',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Location'
        })
        return response

    except Exception as e:
        log(f"Error in WHIP handler: {e}")
        if handler:
            await handler.close()
        return web.Response(status=500, text=str(e))

async def on_shutdown(app):
    coros = [handler.close() for handler in handlers_by_resource_id.values()]
    await asyncio.gather(*coros)
    pcs.clear()
    pcs_by_resource_id.clear()
    handlers_by_resource_id.clear()

def main():
    app = web.Application()
    app.router.add_post(WHIP_ENDPOINT, handle_whip)
    app.on_shutdown.append(on_shutdown)
    
    log(f"Starting WHIP server at http://127.0.0.1:{SERVER_PORT}{WHIP_ENDPOINT}")
    web.run_app(app, port=SERVER_PORT, print=lambda x: log(x))

if __name__ == "__main__":
    main()
