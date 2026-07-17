import requests
import fitz  # PyMuPDF


def download_pdf(pdf_url):
    """
    Downloads PDF from Cloudinary URL
    """

    response = requests.get(pdf_url)

    if response.status_code != 200:
        raise Exception("Unable to download PDF")

    return response.content



def extract_text_from_pdf(pdf_content):
    """
    Extract text from PDF bytes
    """

    document = fitz.open(
        stream=pdf_content,
        filetype="pdf"
    )

    extracted_text = ""


    for page_number, page in enumerate(document):

        text = page.get_text()

        extracted_text += f"\n\nPAGE {page_number + 1}\n"

        extracted_text += text


    document.close()


    return extracted_text