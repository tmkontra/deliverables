# deliverables

A very (very) simple web app to track deliverables and generate invoices.

### Purpose

I kept searching for an off-the-shelf invoicing app that would let me plug in "deliverables". No quantities,
no rates, just `deliverable X` costs `amount Y`.

I finally gave up and built this small app to do just that. I run it locally, and it saves to a sqlite database.

It starts with a "project", a container for deliverables and invoices. I add deliverables as they come up, and can plug them into an invoice as they are finished. This helps me track which deliverables have been invoiced, so I don't bill for the same thing twice.

### Screenshots

Project List (i.e. home screen, index)

![project list](./docs/images/projects.png)

Project Detail

![project detail](./docs/images/project-detail.png)

Project Invoices List
![project invoices](./docs/images/project-invoices.png)

Rendered Invoice (save to PDF via browser print dialog)
![rendered invoice](./docs/images/invoice-render.png)


### TODO

- Support archiving invoices, deliverables
- Switch to soft-deletes (currently, all deletes are "hard" SQL `DELETE`)
- Deploy a private instance so I can log in from anywhere
- Deploy a public demo instance
  - I have this silly idea to generate a session id in the browser cookie, and use that as a "tenant ID"
  - This way, demo users can only see the projects they've added
  - I'd really like to use a "sqlite-db-per-user" and just map the session cookie to a db file, but we will see if SQLAlchemy can play along.