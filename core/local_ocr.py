import json
import platform
import subprocess
import tempfile
from pathlib import Path


def recognize_image(image):
    if platform.system() != 'Windows':
        raise RuntimeError('This OCR backend needs Windows 10/11 and an installed OCR language')
    image = image.convert('RGB')
    image.thumbnail((2500, 2500))
    with tempfile.TemporaryDirectory(prefix='jarvis-ocr-') as folder:
        target = Path(folder) / 'page.png'
        image.save(target)
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File',
            str(Path(__file__).with_name('windows_ocr.ps1')), '-ImagePath', str(target)],
            capture_output=True, timeout=50, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('Windows OCR failed: ' + result.stderr[-1000:])
        return json.loads(result.stdout.lstrip('\ufeff'))


def read_ocr(path, first_page=1, count=3):
    from PIL import Image
    source = Path(path).expanduser().resolve(strict=True)
    if source.stat().st_size > 10_000_000:
        raise ValueError('OCR source exceeds 10 MB')
    if type(first_page) is not int or first_page < 1 or not 1 <= count <= 10:
        raise ValueError('Choose page >=1 and 1-10 pages per OCR request')
    segments = []
    if source.suffix.lower() == '.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(source)) as pdf:
            total = len(pdf)
            if first_page > total:
                raise ValueError('Page exceeds PDF length')
            for index in range(first_page-1, min(total, first_page-1+count)):
                page = pdf[index]
                width, height = page.get_size()
                bitmap = page.render(scale=min(2, 2500/max(width,height)))
                try:
                    data = recognize_image(bitmap.to_pil())
                    segments.append({'page': index+1, **data})
                finally:
                    bitmap.close(); page.close()
    elif source.suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.tif','.tiff'):
        with Image.open(source) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError('OCR image exceeds 40 megapixels')
            segments.append({'page': 1, **recognize_image(image)})
        total = 1
    else:
        raise ValueError('Choose a PDF or supported raster image')
    return {'path': str(source), 'segments': segments, 'total_pages': total,
            'next_page': first_page + count if first_page + count <= total else None,
            'warning': 'OCR is a transcription, not verified ground truth. Check prices, dates and identifiers against the source image.'}
