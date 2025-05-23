import json
import os
from base64 import b64encode
from glob import glob
from io import StringIO
from typing import Tuple, Union

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger
from numpy.distutils.lib2def import output_def

import magic_pdf.model as model_config
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.data.data_reader_writer import DataWriter, FileBasedDataWriter, FileBasedDataReader
from magic_pdf.data.data_reader_writer.s3 import S3DataReader, S3DataWriter
from magic_pdf.data.dataset import PymuDocDataset, ImageDataset

from magic_pdf.libs.config_reader import get_bucket_name, get_s3_config
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.operators.models import InferenceResult
from magic_pdf.operators.pipes import PipeResult


import tempfile
import platform
import shutil
from pathlib import Path
from magic_pdf.utils.office_to_pdf import convert_file_to_pdf as convert_office_file_to_pdf_linux

model_config.__use_inside_model__ = True

app = FastAPI()


class MemoryDataWriter(DataWriter):
    def __init__(self):
        self.buffer = StringIO()

    def write(self, path: str, data: bytes) -> None:
        if isinstance(data, str):
            self.buffer.write(data)
        else:
            self.buffer.write(data.decode("utf-8"))

    def write_string(self, path: str, data: str) -> None:
        self.buffer.write(data)

    def get_value(self) -> str:
        return self.buffer.getvalue()

    def close(self):
        self.buffer.close()



def encode_image(image_path: str) -> str:
    """Encode image using base64"""
    with open(image_path, "rb") as f:
        return b64encode(f.read()).decode()



def convert_office_file_to_pdf_windows(input_path, output_folder):
    import win32com.client
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Get file extension
    _, ext = os.path.splitext(input_path)
    ext = ext.lower()

    # Initialize the correct Office application
    if ext not in [".docx", ".xlsx",  ".pptx" ]:
        raise ValueError("Unsupported file format")

    if ext == ".docx":
        app = win32com.client.Dispatch("Word.Application")
    elif ext == ".xlsx":
        app = win32com.client.Dispatch("Excel.Application")
    else:
        app = win32com.client.Dispatch("PowerPoint.Application")


    try:
        # Convert to PDF
        output_path = os.path.join(output_folder, os.path.basename(input_path).replace(ext, ".pdf"))

        if ext == ".docx":
            doc = app.Documents.Open(input_path)
            doc.SaveAs(output_path, FileFormat=17)  # 17 = PDF format
            doc.Close()
        elif ext == ".xlsx":
            workbook = app.Workbooks.Open(input_path)
            workbook.ExportAsFixedFormat(0, output_path)  # 0 = PDF format
            workbook.Close()
        else:
            ppt = app.Presentations.Open(input_path)
            ppt.SaveAs(output_path, 32)  # 32 = PDF format
            ppt.Close()

        print(f"Successfully converted: {input_path} → {output_path}")
    except Exception as e:
        print(f"Error converting {input_path}: {e}")
    finally:
        app.Quit()


def convert_image_to_pdf(input_path, output_folder):
    ''' 将图片转换成pdf '''
    import img2pdf

    pic_name, _ = os.path.splitext(input_path)
    output_path = os.path.join(output_folder, f"{pic_name}.pdf")

    os.makedirs(output_folder, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(input_path))


def init_writers(
    file_path: str = None,
    output_path: str = None,
    output_image_path: str = None,
) -> Tuple[
    Union[S3DataWriter, FileBasedDataWriter],
    Union[S3DataWriter, FileBasedDataWriter],
    bytes,
]:
    """
    """

    writer = FileBasedDataWriter(output_path)
    image_writer = FileBasedDataWriter(output_image_path)
    os.makedirs(output_image_path, exist_ok=True)
    reader = FileBasedDataReader()
    file_bytes = reader.read(file_path)
    return writer, image_writer, file_bytes

def process_file(
    file_bytes: bytes,
    parse_method: str,
    image_writer: Union[S3DataWriter, FileBasedDataWriter],
) -> Tuple[InferenceResult, PipeResult]:
    """
    Process PDF file content

    Args:
        pdf_bytes: Binary content of PDF file
        parse_method: Parse method ('ocr', 'txt', 'auto')
        image_writer: Image writer

    Returns:
        Tuple[InferenceResult, PipeResult]: Returns inference result and pipeline result
    """


    ds = PymuDocDataset(file_bytes)
    infer_result: InferenceResult = None
    pipe_result: PipeResult = None

    if parse_method == "ocr":
        infer_result = ds.apply(doc_analyze, ocr=True)
        pipe_result = infer_result.pipe_ocr_mode(image_writer)
    elif parse_method == "txt":
        infer_result = ds.apply(doc_analyze, ocr=False)
        pipe_result = infer_result.pipe_txt_mode(image_writer)
    else:  # auto
        if ds.classify() == SupportedPdfParseMethod.OCR:
            infer_result = ds.apply(doc_analyze, ocr=True)
            pipe_result = infer_result.pipe_ocr_mode(image_writer)
        else:
            infer_result = ds.apply(doc_analyze, ocr=False)
            pipe_result = infer_result.pipe_txt_mode(image_writer)

    return infer_result, pipe_result


async def save_file_to_local(upload_file: UploadFile, output_path):
    '''将上传的文件保存到本地'''
    contents = await upload_file.read()
    # 保存文件
    save_path = os.path.join(output_path, upload_file.filename)
    with open(save_path, "wb") as f:
        f.write(contents)

    return save_path


@app.post(
    "/file_process",
    tags=["projects"],
    summary="process different kind of file, such as ppt, word, pdf, png, jpg",
)
async def file_process(
    upload_file: UploadFile,
    parse_method: str = "auto",
    is_json_md_dump: bool = False,
    output_dir: str = "output",
    return_layout: bool = False,
    return_info: bool = False,
    return_content_list: bool = False,
    return_images: bool = False,
):
    try:
        ## 解析上传的文档名称和文档类型
        file_name, ext = os.path.splitext(upload_file.filename)
        ext = ext.lower()

        ## 判断文件类型是否符合要求
        if ext not in ['.pdf', '.docx', '.doc', '.ppt', '.pptx', '.png', '.jpg', '.jpeg']:
            return JSONResponse(
                content={"error": f"unsupport file type:{ext}"},
                status_code=400,
            )

        ## 创建临时文件夹，保存上传文档
        temp_dir = tempfile.mkdtemp()
        temp_file_path = await save_file_to_local(upload_file, temp_dir)

        ## 如果是office格式的文档，则转换成pdf
        process_file_name = temp_file_path
        plat = platform.system()
        if ext in [ '.docx', '.doc', '.ppt', '.pptx']:
            if plat == "Windows":
                convert_office_file_to_pdf_windows(temp_file_path, temp_dir)
            else:
                convert_office_file_to_pdf_linux(temp_file_path, temp_dir)

            process_file_name = os.path.join(temp_dir, f"{file_name}.pdf")

        elif ext in ['.png', '.jpg', '.jpeg']:
            convert_image_to_pdf(temp_file_path, temp_dir)
            process_file_name = os.path.join(temp_dir, f"{file_name}.pdf")



        output_path = os.path.join(output_dir, file_name)
        output_image_path = os.path.join(output_path, "images")

        # Initialize readers/writers and get PDF content
        writer, image_writer, file_bytes = init_writers(
            file_path=process_file_name,
            output_path=output_path,
            output_image_path=output_image_path,
        )

        ## 删除临时文件夹
        shutil.rmtree(temp_dir)

        # Process file
        infer_result, pipe_result = process_file(file_bytes, parse_method, image_writer)

        # Use MemoryDataWriter to get results
        content_list_writer = MemoryDataWriter()
        md_content_writer = MemoryDataWriter()
        middle_json_writer = MemoryDataWriter()

        # Use PipeResult's dump method to get data
        pipe_result.dump_content_list(content_list_writer, "", "images")
        pipe_result.dump_md(md_content_writer, "", "images")
        pipe_result.dump_middle_json(middle_json_writer, "")

        # Get content
        content_list = json.loads(content_list_writer.get_value())
        md_content = md_content_writer.get_value()
        middle_json = json.loads(middle_json_writer.get_value())
        model_json = infer_result.get_infer_res()

        # If results need to be saved
        if is_json_md_dump:
            writer.write_string(
                f"{file_name}_content_list.json", content_list_writer.get_value()
            )
            writer.write_string(f"{file_name}.md", md_content)
            writer.write_string(
                f"{file_name}_middle.json", middle_json_writer.get_value()
            )
            writer.write_string(
                f"{file_name}_model.json",
                json.dumps(model_json, indent=4, ensure_ascii=False),
            )
            # Save visualization results
            pipe_result.draw_layout(os.path.join(output_path, f"{file_name}_layout.pdf"))
            pipe_result.draw_span(os.path.join(output_path, f"{file_name}_spans.pdf"))
            pipe_result.draw_line_sort(
                os.path.join(output_path, f"{file_name}_line_sort.pdf")
            )
            infer_result.draw_model(os.path.join(output_path, f"{file_name}_model.pdf"))

        # Build return data
        data = {}
        if return_layout:
            data["layout"] = model_json
        if return_info:
            data["info"] = middle_json
        if return_content_list:
            data["content_list"] = content_list
        if return_images:
            image_paths = glob(f"{output_image_path}/*.jpg")
            data["images"] = {
                os.path.basename(
                    image_path
                ): f"data:image/jpeg;base64,{encode_image(image_path)}"
                for image_path in image_paths
            }
        data["md_content"] = md_content  # md_content is always returned

        # Clean up memory writers
        content_list_writer.close()
        md_content_writer.close()
        middle_json_writer.close()

        return JSONResponse(data, status_code=200)

    except Exception as e:
        logger.exception(e)
        return JSONResponse(content={"error": str(e)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
