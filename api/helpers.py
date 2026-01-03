from flask import jsonify

class APIResponse:
    @staticmethod
    def success(data=None, message="Success"):
        return jsonify({"status": "success", "message": message, "data": data}), 200

    @staticmethod
    def error(message="Error", code=400):
        return jsonify({"status": "error", "message": message}), code
