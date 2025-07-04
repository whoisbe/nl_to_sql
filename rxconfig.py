import reflex as rx

config = rx.Config(
    app_name="nl_to_sql",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)