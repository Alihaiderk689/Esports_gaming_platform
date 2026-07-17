import cloudinary.uploader


def upload_pdf(file):
    result = cloudinary.uploader.upload(
        file,
        resource_type="raw",
        folder="esports_rules"
    )

    return {
        "url": result["secure_url"],
        "public_id": result["public_id"]
    }


def delete_pdf(public_id):
    cloudinary.uploader.destroy(public_id, resource_type="raw")
