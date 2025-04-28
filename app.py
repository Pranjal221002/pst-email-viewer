import io
import os
import uuid
import re
import magic
import mimetypes
import hashlib
from shutil import copyfile
from flask import Flask, request, render_template, send_file, session, abort
from werkzeug.utils import secure_filename
from utils import extract_emails, search_emails
from semantic_utils import SemanticEmailIndex
import logging

logging.basicConfig(
    filename="app.log",  
    filemode="a", 
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


app = Flask(__name__)
app.secret_key = "your_secret_key"

UPLOAD_FOLDER = "uploads"
EMBED_DIR = "embeddings"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EMBED_DIR, exist_ok=True)

attachment_store = {}
semantic_cache = {}

def enrich_attachment(att):
    data = att["data"]
    mime = magic.Magic(mime=True)
    mime_type = mime.from_buffer(data)
    att["type"] = mime_type

    extension = mimetypes.guess_extension(mime_type) or ".bin"
    if "." not in att["name"]:
        att["name"] += extension

    return att

@app.route("/", methods=["GET", "POST"])
def index():
    emails = []
    query = ""
    error = ""
    pst_path = session.get("pst_path", "")
    pst_filename = session.get("pst_filename", "")

    if request.method == "POST" and 'search' in request.form:
        query = request.form.get("query", "").strip()
        logging.info(f"Search query submitted: '{query}'")

        # Get both inputs
        pst_path_input = request.form.get("pst_path", "").strip()
        embedded_path = request.form.get("embedded_path", "").strip()

        # Prefer embedded dropdown path if selected
        if embedded_path:
            pst_path = embedded_path
            session["pst_path"] = embedded_path
            session["pst_filename"] = os.path.basename(embedded_path)
            logging.info(f"Using embedded PST file: {embedded_path}")

        # Fallback to manual path input
        elif pst_path_input:
            if os.path.exists(pst_path_input):
                try:
                    file_hash = hashlib.md5((pst_path_input + str(os.path.getsize(pst_path_input))).encode()).hexdigest()
                    original_filename = os.path.basename(pst_path_input)
                    unique_filename = f"{file_hash}_{secure_filename(original_filename)}"
                    uploaded_path = os.path.join(UPLOAD_FOLDER, unique_filename)

                    # Avoid duplicate upload if already exists
                    if not os.path.exists(uploaded_path):
                        copyfile(pst_path_input, uploaded_path)
                        logging.info(f"Copied file to: {uploaded_path}")
                    else:
                        logging.info(f"File already exists: {uploaded_path}")

                    pst_path = uploaded_path
                    session["pst_path"] = uploaded_path
                    session["pst_filename"] = original_filename
                except Exception as e:
                    error = f"Error copying PST file: {e}"
                    logging.error(error)
            else:
                error = "Manual path provided does not exist."
                logging.error(error)

        # Continue only if pst_path is valid
        if pst_path and os.path.exists(pst_path):
            try:
                index_key = os.path.basename(pst_path).replace(".pst", "")
                stored_path = os.path.join(EMBED_DIR, index_key)

                if index_key not in semantic_cache:
                    index = SemanticEmailIndex()

                    if os.path.exists(f"{stored_path}.index") and os.path.exists(f"{stored_path}.meta"):
                        index.load(stored_path)
                        logging.info(f"Loaded semantic index from disk: {stored_path}")

                        # ✅ Rebuild attachment store from loaded emails
                        emails = index.emails
                        for email in emails:
                            for att in email["attachments"]:
                                token = str(uuid.uuid4())
                                att["token"] = token
                                att = enrich_attachment(att)
                                attachment_store[token] = att
                    else:
                        emails = extract_emails(pst_path)
                        logging.info(f"Extracted {len(emails)} emails from: {pst_path}")
                        for email in emails:
                            for att in email["attachments"]:
                                token = str(uuid.uuid4())
                                att["token"] = token
                                att = enrich_attachment(att)
                                attachment_store[token] = att

                        index.build_index(emails)
                        index.save(stored_path)
                        logging.info(f"Built and saved new semantic index: {stored_path}")

                    semantic_cache[index_key] = index
                else:
                    index = semantic_cache[index_key]
                    emails = index.emails
                    logging.info(f"Using cached semantic index: {index_key}")

                # Perform search
                if query:
                    if query.startswith("~"):
                        semantic_query = query[1:].strip()
                        emails = index.search(semantic_query)
                        logging.info(f"Semantic search for: {semantic_query}")
                    else:
                        emails = search_emails(emails, query)
                        logging.info(f"Keyword search for: {query}")

            except Exception as e:
                error = f"Failed to search emails: {e}"
                logging.error(error)
        else:
            error = "No PST file stored or invalid path provided."
            logging.error(error)

    # Populate dropdown list
    embedded_files = []
    for fname in os.listdir(UPLOAD_FOLDER):
        if fname.endswith(".pst"):
            index_key = fname.replace(".pst", "")
            index_file = os.path.join(EMBED_DIR, f"{index_key}.index")
            if os.path.exists(index_file):
                full_path = os.path.join(UPLOAD_FOLDER, fname)
                display_name = "_".join(fname.split("_")[1:]) if "_" in fname else fname
                embedded_files.append({
                    "name": display_name,
                    "path": full_path
                })

    return render_template(
        "index.html",
        emails=emails,
        query=query,
        pst_path=pst_path,
        error=error,
        pst_filename=pst_filename,
        embedded_files=embedded_files
    )

@app.route("/download/<token>")
def download_attachment(token):
    att = attachment_store.get(token)
    if not att:
        logging.warning(f"Attachment not found for token: {token}")
        abort(404, description="Attachment not found")

    try:
        logging.info(f"Downloading attachment: {att['name']}")
        return send_file(
            io.BytesIO(att["data"]),
            download_name=att["name"],
            as_attachment=True,
            mimetype=att["type"]
        )
    except Exception as e:
        logging.error(f"Download error: {e}")
        return f"Download error: {e}", 500

if __name__ == "__main__":
    logging.info("Starting Flask application...")
    app.run(debug=True)
