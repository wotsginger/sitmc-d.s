from flask import Flask, send_from_directory, session, abort, jsonify, render_template, request, redirect
import os
from urllib.parse import quote, unquote, urlparse, urlunparse
from threading import Lock
import json

app = Flask(__name__)
app.secret_key = ''  # Change this to a secure random key in production

root_path = "download"
download_counts_file = 'download_counts.json'
lock = Lock()
if not os.path.exists(root_path):
    os.makedirs(root_path, exist_ok=True)


def under_root(*path: str):
    return os.path.join(root_path, *path)


def load_download_counts():
    try:
        with open(download_counts_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("未找到下载次数文件，初始化为空字典。")
        return {}
    except json.JSONDecodeError as e:
        print(f"解析JSON时出错：{e}，初始化为空字典。")
        return {}


def save_download_counts(new_download_counts):
    try:
        with open(download_counts_file, 'w') as file:
            json.dump(new_download_counts, file)
    except Exception as e:
        print(f"写入文件时出错：{e}")


def normalize_path(path: str) -> str:
    # 规范化路径，同时处理 URL 编码问题
    path = os.path.normpath(path)
    return unquote(path)


download_counts = load_download_counts()


@app.route('/')
def index():
    links = []
    for file in os.listdir(root_path):
        file_path = os.path.join(root_path, file)
        if os.path.isdir(file_path):
            links.append(f'<a href="/files/{quote(file)}">{file}</a><br>')
        elif os.path.isfile(file_path):
            links.append(f'<a href="/prepare-download/{quote(file)}">{file}</a><br>')
    return ''.join(links)


@app.route('/files/<path:directory>')
def show_files(directory):
    directory = normalize_path(directory)
    print(f"Requested directory: {directory}")  # 添加调试输出
    if '../' in directory or not os.path.exists(under_root(directory)):
        print(f"Directory not found: {directory}")  # 添加调试输出
        abort(404)
    files_path = under_root(directory)
    files = os.listdir(files_path)
    links = []
    for file in files:
        links.append(f'<a href="/prepare-download/{quote(directory)}/{quote(file)}">{file}</a><br>')
    return ''.join(links)


def extract_download_path_for_url(path: str):
    directory, filename = os.path.split(path)
    url = ""
    if directory:
        url += directory
        url += "/"
    if filename:
        url += filename
    return url


@app.route('/prepare-download/<path:path>')
def prepare_download(path):
    path = normalize_path(path)
    if '../' in path:
        abort(404)
    download_url = "/download/"
    download_url += extract_download_path_for_url(path)
    download_url = unquote(download_url)
    redirect_url = "http://www.sitmc.club/congratulations"
    total_downloads = sum(download_counts.values())
    return render_template('download.html', download_url=download_url, redirect_url=redirect_url,
                           total_downloads=total_downloads)


@app.route('/download/<path:path>')
def download_file(path):
    path = normalize_path(path)
    if '../' in path:
        abort(404)
    download_path = extract_download_path_for_url(path)
    download_path = unquote(download_path)
    file_path = normalize_path(under_root(download_path))

    if 'downloaded_files' not in session:
        session['downloaded_files'] = []
    if file_path not in session['downloaded_files']:
        with lock:
            if file_path in download_counts:
                download_counts[file_path] += 1
            else:
                download_counts[file_path] = 1
            save_download_counts(download_counts)
        session['downloaded_files'].append(file_path)
        session.modified = True
    return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), as_attachment=True)


def validate_auth():
    # 验证密钥
    if 'Authorization' not in request.headers or request.headers['Authorization'] != app.secret_key:
        abort(403)  # 禁止访问


def allowed_file(file):
    content_type = file.content_type
    # allow images
    if content_type.startswith("image"):
        return True
    # allow zip archive
    if content_type == "application/zip":
        return True
    # allow *.jar for Minecraft mods
    if content_type == "application/java-archive":
        return True
    # allow *.apk archive
    if content_type == "application/vnd.android.package-archive":
        return True

    return False


@app.route('/admin', methods=['PUT'])
def admin_upload():
    validate_auth()

    # 获取文件路径和文件名
    path = normalize_path(request.form.get('path', ''))
    filename = request.form.get('file', '').lower()  # 转换为小写以处理不区分大小写的情况

    # 防止目录遍历
    if '../' in path or '../' in filename:
        abort(400)

    file = request.files['file']

    if not file or file.filename == '':
        return jsonify({"error": "没有选择要上传的文件"}), 400
    if not allowed_file(file):
        return jsonify({"error": "文件类型不允许"}), 400

    # 完整的文件路径
    local_path = normalize_path(under_root(path))
    # create parent dir
    if not os.path.exists(os.path.dirname(local_path)):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if os.path.isdir(local_path):
        os.rmdir(local_path)

    file.save(local_path)
    relative_file_path = os.path.relpath(local_path, root_path)
    return jsonify({"message": "文件上传成功", "path": relative_file_path}), 201


@app.route('/admin', methods=['DELETE'])
def admin_delete():
    validate_auth()

    # 获取文件路径
    path = normalize_path(request.form.get('path', '').lower())

    # 防止目录遍历
    if '../' in path:
        abort(400)

    # 完整的文件路径
    local_path = normalize_path(under_root(path))
    if os.path.exists(local_path):
        try:
            os.unlink(local_path)
            return jsonify({"message": "文件删除成功"}), 200
        except OSError as e:
            return jsonify({"error": f"文件删除失败：{e}"}), 500
    else:
        return jsonify({"error": "文件不存在"}), 200

@app.route('/admin/upload', methods=['POST'])
def admin_upload_post():
    validate_auth()

    path = normalize_path(request.form.get('path', ''))
    filename = request.form.get('file', '').lower()  # 转换为小写以处理不区分大小写的情况

    if '../' in path or '../' in filename:
        abort(400)

    file = request.files['file']

    if not file or file.filename == '':
        return jsonify({"error": "没有选择要上传的文件"}), 400
    if not allowed_file(file):
        return jsonify({"error": "文件类型不允许"}), 400

    local_path = normalize_path(under_root(path, file.filename))

    if not os.path.exists(os.path.dirname(local_path)):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if os.path.isdir(local_path):
        return jsonify({"error": "目标路径是目录，无法上传文件"}), 400

    # Save the file
    file.save(local_path)
    relative_file_path = os.path.relpath(local_path, root_path)
    return jsonify({"message": "文件上传成功", "path": relative_file_path}), 201


@app.route('/stats')
def show_stats():
    total_downloads = sum(download_counts.values())
    detailed_stats = {os.path.basename(key): value for key, value in download_counts.items()}
    return jsonify(total_downloads=total_downloads, detailed_stats=detailed_stats)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
