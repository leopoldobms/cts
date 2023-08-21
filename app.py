from flask import Flask
from packages.routes import routes

app = Flask(__name__)
app.register_blueprint(routes)


@app.route('/')
def hello():
    return "Hello World!"


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
