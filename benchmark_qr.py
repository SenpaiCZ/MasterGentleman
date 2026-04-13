import time
import qrcode
from io import BytesIO
import asyncio

def generate_qr_sync(fc):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(fc)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

async def benchmark_sync(n=10):
    start = time.perf_counter()
    for i in range(n):
        generate_qr_sync(f"12345678{i:04d}")
    end = time.perf_counter()
    print(f"Sync took: {end - start:.4f}s for {n} QR codes")
    return end - start

async def benchmark_async_threaded(n=10):
    start = time.perf_counter()
    tasks = []
    for i in range(n):
        tasks.append(asyncio.to_thread(generate_qr_sync, f"12345678{i:04d}"))
    await asyncio.gather(*tasks)
    end = time.perf_counter()
    print(f"Async threaded took: {end - start:.4f}s for {n} QR codes")
    return end - start

if __name__ == "__main__":
    asyncio.run(benchmark_sync(50))
    asyncio.run(benchmark_async_threaded(50))
