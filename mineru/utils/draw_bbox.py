import json
import os
from io import BytesIO

from loguru import logger
from pdf2image import convert_from_bytes
from PIL import Image
from pypdf import PdfReader, PdfWriter, PageObject
from reportlab.pdfgen import canvas

from .enum_class import BlockType, ContentType


def cal_canvas_rect(page, bbox):
    """
    Calculate the rectangle coordinates on the canvas based on the original PDF page and bounding box.

    Args:
        page: A PyPDF2 Page object representing a single page in the PDF.
        bbox: [x0, y0, x1, y1] representing the bounding box coordinates.

    Returns:
        rect: [x0, y0, width, height] representing the rectangle coordinates on the canvas.
    """
    page_width, page_height = float(page.cropbox[2]), float(page.cropbox[3])
    
    actual_width = page_width    # The width of the final PDF display
    actual_height = page_height  # The height of the final PDF display
    
    rotation = page.get("/Rotate", 0)
    rotation = rotation % 360
    
    if rotation in [90, 270]:
        # PDF is rotated 90 degrees or 270 degrees, and the width and height need to be swapped
        actual_width, actual_height = actual_height, actual_width
        
    x0, y0, x1, y1 = bbox
    rect_w = abs(x1 - x0)
    rect_h = abs(y1 - y0)
    
    if 270 == rotation:
        rect_w, rect_h = rect_h, rect_w
        x0 = actual_height - y1
        y0 = actual_width - x1
    elif 180 == rotation:
        x0 = page_width - x1
        y0 = y0
    elif 90 == rotation:
        rect_w, rect_h = rect_h, rect_w
        x0, y0 = y0, x0 
    else:
        # 0 == rotation:
        x0 = x0
        y0 = page_height - y1
    
    rect = [x0, y0, rect_w, rect_h]        
    return rect


def draw_bbox_without_number(i, bbox_list, page, c, rgb_config, fill_config):
    new_rgb = [float(color) / 255 for color in rgb_config]
    page_data = bbox_list[i]

    for bbox in page_data:
        rect = cal_canvas_rect(page, bbox)  # Define the rectangle  

        if fill_config:  # filled rectangle
            c.setFillColorRGB(new_rgb[0], new_rgb[1], new_rgb[2], 0.3)
            c.rect(rect[0], rect[1], rect[2], rect[3], stroke=0, fill=1)
        else:  # bounding box
            c.setStrokeColorRGB(new_rgb[0], new_rgb[1], new_rgb[2])
            c.rect(rect[0], rect[1], rect[2], rect[3], stroke=1, fill=0)
    return c


def draw_bbox_with_number(i, bbox_list, page, c, rgb_config, fill_config, draw_bbox=True):
    new_rgb = [float(color) / 255 for color in rgb_config]
    page_data = bbox_list[i]
    # 强制转换为 float
    page_width, page_height = float(page.cropbox[2]), float(page.cropbox[3])

    for j, bbox in enumerate(page_data):
        # 确保bbox的每个元素都是float
        rect = cal_canvas_rect(page, bbox)  # Define the rectangle  
        
        if draw_bbox:
            if fill_config:
                c.setFillColorRGB(*new_rgb, 0.3)
                c.rect(rect[0], rect[1], rect[2], rect[3], stroke=0, fill=1)
            else:
                c.setStrokeColorRGB(*new_rgb)
                c.rect(rect[0], rect[1], rect[2], rect[3], stroke=1, fill=0)
        c.setFillColorRGB(*new_rgb, 1.0)
        c.setFontSize(size=10)
        
        c.saveState()
        rotation = page.get("/Rotate", 0)
        rotation = rotation % 360
    
        if 0 == rotation:
            c.translate(rect[0] + rect[2] + 2, rect[1] + rect[3] - 10)
        elif 90 == rotation:
            c.translate(rect[0] + 10, rect[1] + rect[3] + 2)
        elif 180 == rotation:
            c.translate(rect[0] - 2, rect[1] + 10)
        elif 270 == rotation:
            c.translate(rect[0] + rect[2] - 10, rect[1] - 2)
            
        c.rotate(rotation)
        c.drawString(0, 0, str(j + 1))
        c.restoreState()

    return c


def draw_layout_bbox(pdf_info, pdf_bytes, out_path, filename):
    dropped_bbox_list = []
    tables_list, tables_body_list = [], []
    tables_caption_list, tables_footnote_list = [], []
    imgs_list, imgs_body_list, imgs_caption_list = [], [], []
    imgs_footnote_list = []
    titles_list = []
    texts_list = []
    interequations_list = []
    lists_list = []
    indexs_list = []
    for page in pdf_info:
        page_dropped_list = []
        tables, tables_body, tables_caption, tables_footnote = [], [], [], []
        imgs, imgs_body, imgs_caption, imgs_footnote = [], [], [], []
        titles = []
        texts = []
        interequations = []
        lists = []
        indices = []

        for dropped_bbox in page['discarded_blocks']:
            page_dropped_list.append(dropped_bbox['bbox'])
        dropped_bbox_list.append(page_dropped_list)
        for block in page["para_blocks"]:
            bbox = block["bbox"]
            if block["type"] == BlockType.TABLE:
                tables.append(bbox)
                for nested_block in block["blocks"]:
                    bbox = nested_block["bbox"]
                    if nested_block["type"] == BlockType.TABLE_BODY:
                        tables_body.append(bbox)
                    elif nested_block["type"] == BlockType.TABLE_CAPTION:
                        tables_caption.append(bbox)
                    elif nested_block["type"] == BlockType.TABLE_FOOTNOTE:
                        tables_footnote.append(bbox)
            elif block["type"] == BlockType.IMAGE:
                imgs.append(bbox)
                for nested_block in block["blocks"]:
                    bbox = nested_block["bbox"]
                    if nested_block["type"] == BlockType.IMAGE_BODY:
                        imgs_body.append(bbox)
                    elif nested_block["type"] == BlockType.IMAGE_CAPTION:
                        imgs_caption.append(bbox)
                    elif nested_block["type"] == BlockType.IMAGE_FOOTNOTE:
                        imgs_footnote.append(bbox)
            elif block["type"] == BlockType.TITLE:
                titles.append(bbox)
            elif block["type"] == BlockType.TEXT:
                texts.append(bbox)
            elif block["type"] == BlockType.INTERLINE_EQUATION:
                interequations.append(bbox)
            elif block["type"] == BlockType.LIST:
                lists.append(bbox)
            elif block["type"] == BlockType.INDEX:
                indices.append(bbox)

        tables_list.append(tables)
        tables_body_list.append(tables_body)
        tables_caption_list.append(tables_caption)
        tables_footnote_list.append(tables_footnote)
        imgs_list.append(imgs)
        imgs_body_list.append(imgs_body)
        imgs_caption_list.append(imgs_caption)
        imgs_footnote_list.append(imgs_footnote)
        titles_list.append(titles)
        texts_list.append(texts)
        interequations_list.append(interequations)
        lists_list.append(lists)
        indexs_list.append(indices)

    layout_bbox_list = []

    table_type_order = {"table_caption": 1, "table_body": 2, "table_footnote": 3}
    for page in pdf_info:
        page_block_list = []
        for block in page["para_blocks"]:
            if block["type"] in [
                BlockType.TEXT,
                BlockType.TITLE,
                BlockType.INTERLINE_EQUATION,
                BlockType.LIST,
                BlockType.INDEX,
            ]:
                bbox = block["bbox"]
                page_block_list.append(bbox)
            elif block["type"] in [BlockType.IMAGE]:
                for sub_block in block["blocks"]:
                    bbox = sub_block["bbox"]
                    page_block_list.append(bbox)
            elif block["type"] in [BlockType.TABLE]:
                sorted_blocks = sorted(block["blocks"], key=lambda x: table_type_order[x["type"]])
                for sub_block in sorted_blocks:
                    bbox = sub_block["bbox"]
                    page_block_list.append(bbox)

        layout_bbox_list.append(page_block_list)

    try:
        images = convert_from_bytes(pdf_bytes)
        pdf_reader_for_size = PdfReader(BytesIO(pdf_bytes))
        cleaned_images = []

        for i, page_info in enumerate(pdf_info):
            if i >= len(images):
                logger.warning(f"Page index {i} out of bounds for images list (length {len(images)}).")
                continue
            
            page_image = images[i]

            pdf_page = pdf_reader_for_size.pages[i]
            pdf_width = float(pdf_page.cropbox[2])
            pdf_height = float(pdf_page.cropbox[3])

            scale_w = page_image.width / pdf_width
            scale_h = page_image.height / pdf_height

            new_image = Image.new("RGB", page_image.size, "white")
            
            #dropped_bbox_list[i] +
            all_bboxes_for_page = (
                tables_body_list[i] +
                tables_caption_list[i] +
                tables_footnote_list[i] +
                imgs_body_list[i] +
                imgs_caption_list[i] +
                imgs_footnote_list[i] +
                titles_list[i] +
                texts_list[i] +
                interequations_list[i] +
                lists_list[i] +
                indexs_list[i]
            )
            #all_bboxes_for_page = ([texts_list[i][-1]])

            for bbox in all_bboxes_for_page:
                pil_box = (
                    bbox[0] * scale_w,
                    bbox[1] * scale_h,
                    bbox[2] * scale_w,
                    bbox[3] * scale_h
                )
                
                pil_box_safe = (
                    max(0, pil_box[0]),
                    max(0, pil_box[1]),
                    min(page_image.width, pil_box[2]),
                    min(page_image.height, pil_box[3])
                )

                if pil_box_safe[0] < pil_box_safe[2] and pil_box_safe[1] < pil_box_safe[3]:
                    cropped_content = page_image.crop(pil_box_safe)
                    paste_position = (int(pil_box_safe[0]), int(pil_box_safe[1]))
                    new_image.paste(cropped_content, paste_position)
            
            cleaned_images.append(new_image)

        if cleaned_images:
            base_name, _ = os.path.splitext(filename)
            base_name = base_name.replace("layout_", "")
            clean_pdf_filename = f"{base_name}_clean.pdf"
            output_pdf_path = os.path.join(out_path, clean_pdf_filename)

            first_image = cleaned_images[0]
            if first_image.mode != 'RGB':
                first_image = first_image.convert('RGB')
            
            append_list = []
            for img in cleaned_images[1:]:
                if img.mode != 'RGB':
                    append_list.append(img.convert('RGB'))
                else:
                    append_list.append(img)

            first_image.save(
                output_pdf_path, "PDF", resolution=100.0, save_all=True, append_images=append_list
            )

    except Exception as e:
        logger.warning(f"Could not generate clean PDF: {e}")

    pdf_bytes_io = BytesIO(pdf_bytes)
    pdf_docs = PdfReader(pdf_bytes_io)
    output_pdf = PdfWriter()

    for i, page in enumerate(pdf_docs.pages):
        page_width, page_height = float(page.cropbox[2]), float(page.cropbox[3])
        custom_page_size = (page_width, page_height)

        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=custom_page_size)

        c = draw_bbox_without_number(i, dropped_bbox_list, page, c, [158, 158, 158], True)
        c = draw_bbox_without_number(i, tables_body_list, page, c, [204, 204, 0], True)
        c = draw_bbox_without_number(i, tables_caption_list, page, c, [255, 255, 102], True)
        c = draw_bbox_without_number(i, tables_footnote_list, page, c, [229, 255, 204], True)
        c = draw_bbox_without_number(i, imgs_body_list, page, c, [153, 255, 51], True)
        c = draw_bbox_without_number(i, imgs_caption_list, page, c, [102, 178, 255], True)
        c = draw_bbox_without_number(i, imgs_footnote_list, page, c, [255, 178, 102], True)
        c = draw_bbox_without_number(i, titles_list, page, c, [102, 102, 255], True)
        c = draw_bbox_without_number(i, texts_list, page, c, [153, 0, 76], True)
        c = draw_bbox_without_number(i, interequations_list, page, c, [0, 255, 0], True)
        c = draw_bbox_without_number(i, lists_list, page, c, [40, 169, 92], True)
        c = draw_bbox_without_number(i, indexs_list, page, c, [40, 169, 92], True)
        c = draw_bbox_with_number(i, layout_bbox_list, page, c, [255, 0, 0], False, draw_bbox=False)

        c.save()
        packet.seek(0)
        overlay_pdf = PdfReader(packet)

        if len(overlay_pdf.pages) > 0:
            new_page = PageObject(pdf=None)
            new_page.update(page)
            page = new_page
            page.merge_page(overlay_pdf.pages[0])
        else:
            pass

        output_pdf.add_page(page)

    with open(f"{out_path}/{filename}", "wb") as f:
        output_pdf.write(f)


def draw_span_bbox(pdf_info, pdf_bytes, out_path, filename):
    last_span_bboxes = []
    next_page_text_spans_bboxes = []

    for page in pdf_info:
        page_text_spans_bboxes = []
        if next_page_text_spans_bboxes:
            page_text_spans_bboxes.extend(next_page_text_spans_bboxes)
            next_page_text_spans_bboxes.clear()

        for block in page.get('preproc_blocks', []):
            if block.get('type') in [
                BlockType.TEXT, BlockType.TITLE, BlockType.INTERLINE_EQUATION,
                BlockType.LIST, BlockType.INDEX,
            ]:
                for line in block.get('lines', []):
                    for span in line.get('spans', []):
                        if span.get('type') == ContentType.TEXT:
                            if span.get('cross_page', False):
                                next_page_text_spans_bboxes.append(span['bbox'])
                            else:
                                page_text_spans_bboxes.append(span['bbox'])
            elif block.get('type') in [BlockType.IMAGE, BlockType.TABLE]:
                for sub_block in block.get('blocks', []):
                    for line in sub_block.get('lines', []):
                        for span in line.get('spans', []):
                            if span.get('type') == ContentType.TEXT:
                                if span.get('cross_page', False):
                                    next_page_text_spans_bboxes.append(span['bbox'])
                                else:
                                    page_text_spans_bboxes.append(span['bbox'])
        
        if page_text_spans_bboxes:
            last_span_bboxes.append(page_text_spans_bboxes[-1])
        else:
            last_span_bboxes.append(None)

    # Image processing part
    try:
        images = convert_from_bytes(pdf_bytes)
        pdf_reader_for_size = PdfReader(BytesIO(pdf_bytes))

        img_dir = os.path.join(out_path, "lastline")
        os.makedirs(img_dir, exist_ok=True)

        for i in range(len(pdf_info)):
            if i >= len(images):
                logger.warning(f"Page index {i} out of bounds for images list (length {len(images)}).")
                continue
            
            last_span_bbox = last_span_bboxes[i]
            if not last_span_bbox:
                logger.warning(f"No text spans found for page {i}.")
                continue

            page_image = images[i]
            pdf_page = pdf_reader_for_size.pages[i]
            pdf_width = float(pdf_page.cropbox[2])
            pdf_height = float(pdf_page.cropbox[3])
            scale_w = page_image.width / pdf_width
            scale_h = page_image.height / pdf_height

            bbox = last_span_bbox
            pil_box = (
                bbox[0] * scale_w,
                bbox[1] * scale_h,
                bbox[2] * scale_w,
                bbox[3] * scale_h
            )
            
            pil_box_safe = (
                max(0, pil_box[0]),
                max(0, pil_box[1]),
                min(page_image.width, pil_box[2]),
                min(page_image.height, pil_box[3])
            )


            if pil_box_safe[0] < pil_box_safe[2] and pil_box_safe[1] < pil_box_safe[3]:
                cropped_content = page_image.crop(pil_box_safe)
                output_image_path = os.path.join(img_dir, f"page_{i:03d}_lastline.png")
                cropped_content.save(output_image_path, "PNG")

    except Exception as e:
        logger.warning(f"Could not extract last line images: {e}")


if __name__ == "__main__":
    # 读取PDF文件
    pdf_path = "/Users/xucui/dev/scan/small/jianming_part.pdf"
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # 从json文件读取pdf_info

    json_path = "/tmp/a/jianming_part/auto/jianming_part_middle.json"
    with open(json_path, "r", encoding="utf-8") as f:
        pdf_ann = json.load(f)
    pdf_info = pdf_ann["pdf_info"]

    out_path = "/tmp/examples"
    print("checkout output in:", out_path)
    # 调用可视化函数,输出到examples目录
    draw_layout_bbox(pdf_info, pdf_bytes, out_path, "output_with_layout.pdf")


    draw_span_bbox(pdf_info, pdf_bytes, out_path, "output_with_span_1.pdf")
