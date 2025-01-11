import json
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind

# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'course_catalog.json'

#Logging in JSON format
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'filename': record.pathname,
            'line': record.lineno
        }
        return json.dumps(log_entry, indent=4)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Log to file
        logging.StreamHandler()          # Log to console
    ]
)

# OpenTelemetry Setup
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
FlaskInstrumentor().instrument_app(app)


# Utility Functions
def load_courses():
    """Load courses from the JSON file."""
    if not os.path.exists(COURSE_FILE):
        return []  # Return an empty list if the file doesn't exist
    with open(COURSE_FILE, 'r') as file:
        return json.load(file)


def save_courses(data):
    """Save new course data to the JSON file."""
    courses = load_courses()  # Load existing courses
    courses.append(data)  # Append the new course
    with open(COURSE_FILE, 'w') as file:
        json.dump(courses, file, indent=4)


# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/catalog')
def course_catalog():
    courses = load_courses()
    logging.info(f"Accessed the course catalog. Total courses: {len(courses)}.")
    return render_template('course_catalog.html', courses=courses)


@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':

        required_fields = ['code', 'name', 'instructor', 'semester']
        missing_fields = [field for field in required_fields if not request.form.get(field)]
        
        if missing_fields:
            error_message = f"Required fields missing: {', '.join(missing_fields)}"
            flash(error_message, "error")
            logging.error(error_message)
            return redirect(url_for('add_course'))

        course = {
            'code': request.form['code'],
            'name': request.form['name'],
            'instructor': request.form['instructor'],
            'semester': request.form['semester'],
            'schedule': request.form['schedule'],
            'classroom': request.form['classroom'],
            'prerequisites': request.form['prerequisites'],
            'grading': request.form['grading'],
            'description': request.form['description']
        }
        save_courses(course)
        flash(f"Course '{course['name']}' added successfully!", "success")
        logging.info(f"Added new course: {course}")
        return redirect(url_for('course_catalog'))
    logging.info("Accessed the add course page")
    return render_template('add_course.html')


@app.route('/course/<code>')
def course_details(code):
    courses = load_courses()
    course = next((course for course in courses if course['code'] == code), None)
    if not course:
        error_message = f"No course with code '{code}' found"
        logging.error(error_message)
        flash(f"No course with code '{code}' found", "error")
        return redirect(url_for('course_catalog'))
    logging.info(f"Accessed details for course '{course['name']}' with code '{code}'")
    return render_template('course_details.html', course=course)


@app.route("/manual-trace")
def manual_trace():
    # Start a span manually for custom tracing
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Processing request")
        logging.info("Manual trace executed")
        return "Manual trace recorded", 200


@app.route("/auto-instrumented")
def auto_instrumented():
    # Automatically instrumented via FlaskInstrumentor
    logging.info("Accessed auto-instrumented route")
    return "This route is auto-instrumented", 200


if __name__ == '__main__':
    app.run(debug=True)
