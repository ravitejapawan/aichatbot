import fitz  # PyMuPDF
import os

pdf_path = "Nx2meApp_UserGuide.pdf"
output_dir = "images"

os.makedirs(output_dir, exist_ok=True)

doc = fitz.open(pdf_path)

for page_index in range(len(doc)):
    page = doc[page_index]
    image_list = page.get_images(full=True)

    for img_index, img in enumerate(image_list):
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]

        image_name = f"page_{page_index+1}_fig_{img_index+1}.png"
        with open(os.path.join(output_dir, image_name), "wb") as f:
            f.write(image_bytes)

print("✅ Images extracted successfully!")
