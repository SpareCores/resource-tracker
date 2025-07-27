from re import sub

from resource_tracker.tiny_bars import render_template


def normalize_whitespace(text: str) -> str:
    return sub(r"\s+", " ", text.strip())


def test_tiny_bars_complex_template():
    """Test Tiny Bars template rendering."""

    template = """
    <h1>{{ title }}</h1>
    <p>There are {{ users_length }} users.</p>
    <ul>
        {{#each users as user}}
        <li>
            {{ user.name }} - {{{ user.email }}}
            {{#if user.active}}<strong>Active</strong>{{/if}}
        </li>
        {{/each}}
    </ul>
    """

    context = {
        "title": "User List",
        "users": [
            # test HTML escaping (in name) and raw output (in email) as well
            {"name": "Foo <FooAdmin>", "email": "<foo@example.com>", "active": True},
            {"name": "Bar", "email": "<bar@example.com>", "active": False},
        ],
    }
    context["users_length"] = len(context["users"])

    output = render_template(template, context)
    assert normalize_whitespace(output) == normalize_whitespace("""
    <h1>User List</h1>
    <p>There are 2 users.</p>
    <ul>
        <li>
            Foo &lt;FooAdmin&gt; - <foo@example.com>
            <strong>Active</strong>
        </li>
        <li>
            Bar - <bar@example.com>
        </li>
    </ul>
    """)


def test_tiny_bars_string_list():
    """Test Tiny Bars template rendering with a list of strings."""

    template = """
    <h1>{{ title }}</h1>
    <ul>
        {{#each items as item}}
        <li>{{ item }}</li>
        {{/each}}
    </ul>
    """

    context = {"title": "String List", "items": ["Apple", "Banana", "Cherry"]}

    output = render_template(template, context)
    assert normalize_whitespace(output) == normalize_whitespace("""
    <h1>String List</h1>
    <ul>
        <li>Apple</li>
        <li>Banana</li>
        <li>Cherry</li>
    </ul>
    """)


def test_tiny_bars_nested_access():
    """Test Tiny Bars template rendering with nested property access."""

    template = """
    <h1>{{ title }}</h1>
    <p>First user: {{ data.users.first.name }}</p>
    <p>Second user email: {{ data.users.second.email }}</p>
    <ul>
        {{#each data.users.list as user}}
        <li>
            <p>{{ user.name }}</p>
            {{#if user.active}}
            <p>Active user</p>
            {{/if}}
        </li>
        {{/each}}
    </ul>
    """

    context = {
        "title": "Nested Access",
        "data": {
            "users": {
                "first": {
                    "name": "Alice",
                    "email": "alice@example.com",
                    "active": True,
                },
                "second": {"name": "Bob", "email": "bob@example.com", "active": False},
                "list": [
                    {"name": "Alice", "email": "alice@example.com", "active": True},
                    {"name": "Bob", "email": "bob@example.com", "active": False},
                ],
            }
        },
    }

    output = render_template(template, context)
    assert normalize_whitespace(output) == normalize_whitespace("""
    <h1>Nested Access</h1>
    <p>First user: Alice</p>
    <p>Second user email: bob@example.com</p>
    <ul>
        <li>
            <p>Alice</p>
            <p>Active user</p>
        </li>
        <li>
            <p>Bob</p>
        </li>
    </ul>
    """)


def test_tiny_bars_object_attributes():
    """Test Tiny Bars template rendering with object attributes."""

    template = """
    <h1>{{ title }}</h1>
    <ul>
        {{#each people as person}}
        <li>
            <p>Name: {{ person.name }}</p>
            <p>Age: {{ person.age }}</p>
        </li>
        {{/each}}
    </ul>
    """

    class Person:
        def __init__(self, name, age):
            self.name = name
            self.age = age

    context = {"title": "People", "people": [Person("Alice", 30), Person("Bob", 25)]}

    output = render_template(template, context)
    assert normalize_whitespace(output) == normalize_whitespace("""
    <h1>People</h1>
    <ul>
        <li>
            <p>Name: Alice</p>
            <p>Age: 30</p>
        </li>
        <li>
            <p>Name: Bob</p>
            <p>Age: 25</p>
        </li>
    </ul>
    """)


def test_tiny_bars_if_conditions():
    """Test Tiny Bars if conditions."""

    template = "{{#if value}}True{{/if}}"

    # true value
    context = {"value": True}
    assert render_template(template, context) == "True"

    # false value
    context = {"value": False}
    assert render_template(template, context) == ""

    # truthy value
    context = {"value": "something"}
    assert render_template(template, context) == "True"

    # falsy value
    context = {"value": ""}
    assert render_template(template, context) == ""

    # missing value
    context = {"value": None}
    assert render_template(template, context) == ""
    context = {}
    assert render_template(template, context) == ""

    # numeric values
    context = {"value": 1}
    assert render_template(template, context) == "True"
    context = {"value": 0}
    assert render_template(template, context) == ""


def test_tiny_bars_if_else_conditions():
    """Test Tiny Bars if/else conditions."""

    template = "{{#if value}}True{{#else}}False{{/if}}"

    # true condition
    context = {"value": True}
    assert render_template(template, context) == "True"

    # false condition
    context = {"value": False}
    assert render_template(template, context) == "False"

    # truthy value
    context = {"value": "something"}
    assert render_template(template, context) == "True"

    # falsy value
    context = {"value": ""}
    assert render_template(template, context) == "False"

    # missing value
    context = {"value": None}
    assert render_template(template, context) == "False"
    context = {}
    assert render_template(template, context) == "False"

    # numeric values
    context = {"value": 1}
    assert render_template(template, context) == "True"
    context = {"value": 0}
    assert render_template(template, context) == "False"

    # nested content
    template = """
    {{#if value}}
        <div>True: {{message}}</div>
    {{#else}}
        <div>False: {{message}}</div>
    {{/if}}
    """
    context = {"value": True, "message": "Hello"}
    assert (
        normalize_whitespace(render_template(template, context))
        == "<div>True: Hello</div>"
    )
    context = {"value": False, "message": "Hello"}
    assert (
        normalize_whitespace(render_template(template, context))
        == "<div>False: Hello</div>"
    )

    # nested if/else
    template = """
    {{#if value}}
        <div>True: {{#if value}}True{{/if}}</div>
    {{#else}}
        <div>False{{#if value}}: True{{/if}}</div>
    {{/if}}
    """
    context = {"value": True}
    assert (
        normalize_whitespace(render_template(template, context))
        == "<div>True: True</div>"
    )
    context = {"value": False}
    assert (
        normalize_whitespace(render_template(template, context)) == "<div>False</div>"
    )
