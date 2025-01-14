# Import modules
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
from opentelemetry.trace import SpanKind, Status, StatusCode

# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
course = 'course_catalog.json'

# JSON format for logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'filename': record.pathname,
            'line': record.lineno}
        return json.dumps(log, indent=4)

# Configure Logging
json_format = JsonFormatter()

file_handler = logging.FileHandler("app.log")
file_handler.setFormatter(json_format)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(json_format)

logging.basicConfig(level=logging.INFO,
    handlers=[file_handler, stream_handler])

# OpenTelemetry Setup
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
FlaskInstrumentor().instrument_app(app)

# Load courses from the JSON file
def load_courses():
    if not os.path.exists(course):
        return []  
    with open(course, 'r') as file:
        return json.load(file)

# Save new course data to the JSON file
def save_courses(data):
    courses = load_courses() 
    courses.append(data)  
    with open(course, 'w') as file:
        json.dump(courses, file, indent=4)

# Request Tracing
@app.before_request
def before_request():
    span = trace.get_current_span()
    span.set_attribute("http.method", request.method)
    span.set_attribute("http.url", request.url)

# Error Handler
@app.errorhandler(Exception)
def handle_exception(e):
    span = trace.get_current_span()
    span.set_status(Status(StatusCode.ERROR, str(e)))
    logging.error(f"Unhandled exception: {e}", exc_info=True)
    return "Internal Server Error", 500

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog_span") as span:
        courses = load_courses()
        span.set_attribute("total_courses", len(courses))
        logging.info(f"Accessed course catalog. Total courses: {len(courses)}.")
        return render_template('course_catalog.html', courses=courses)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    with tracer.start_as_current_span("add_course_span") as span:
        if request.method == 'POST':
            required_fields = ['code', 'name', 'instructor', 'semester']
            missing_fields = [field for field in required_fields if not request.form.get(field, '').strip()]
            
            if missing_fields:
                error = f"Required fields missing: {', '.join(missing_fields)}"
                flash(error, "error")
                logging.error(error)
                span.set_status(Status(StatusCode.ERROR, error))
                return redirect(url_for('add_course'))

            course = {
                'code': request.form['code'].strip(),
                'name': request.form['name'].strip(),
                'instructor': request.form['instructor'].strip(),
                'semester': request.form['semester'].strip(),
                'schedule': request.form.get('schedule', '').strip(),
                'classroom': request.form.get('classroom', '').strip(),
                'prerequisites': request.form.get('prerequisites', '').strip(),
                'grading': request.form.get('grading', '').strip(),
                'description': request.form.get('description', '').strip()}
            save_courses(course)
            flash(f"Course '{course['name']}' added successfully!", "success")
            logging.info(f"Added new course: {course}")
            return redirect(url_for('course_catalog'))
        logging.info("Accessed the add course page")
        return render_template('add_course.html')

@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span("course_details_span") as span:
        courses = load_courses()
        course = next((course for course in courses if course['code'] == code), None)
        if not course:
            error = f"No course with code '{code}' found"
            logging.error(error)
            flash(error, "error")
            span.set_status(Status(StatusCode.ERROR, error))
            return redirect(url_for('course_catalog'))
        logging.info(f"Accessed course '{course['name']}' with code '{code}'")
        return render_template('course_details.html', course=course)

@app.route("/manual-trace")
def manual_trace():
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Processing request")
        logging.info("Manual trace executed")
        return "Manual trace recorded", 200

@app.route("/auto-instrumented")
def auto_instrumented():
    logging.info("Accessed auto-instrumented route")
    return "This route is auto-instrumented", 200

if __name__ == '__main__':
    app.run(debug=True)