# Changelog

All notable changes to ProjectForge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2025-01-01

### Added

#### Authentication & Authorization
- User registration with email validation and secure password hashing
- Login and logout with session-based authentication using signed cookies
- Role-Based Access Control (RBAC) with five roles: Super Admin, Project Manager, Developer, QA, and Viewer
- Route-level and template-level permission guards based on user roles
- Password reset functionality with secure token generation

#### User Management
- Admin interface for creating, editing, and deactivating user accounts
- User profile pages with editable display name and contact information
- Role assignment and modification restricted to Super Admin users
- User listing with search, filter by role, and pagination

#### Department Management
- Full CRUD operations for departments
- Department head assignment from existing users
- Department member management with add and remove capabilities
- Department listing with member count and head display

#### Project Management
- Full CRUD operations for projects with status tracking (Planning, Active, On Hold, Completed, Archived)
- Project assignment to departments with department-scoped visibility
- Project member management with role-based access
- Project detail pages with associated sprints, tickets, and team members
- Project listing with filters for status and department

#### Sprint Management
- Full CRUD operations for sprints within projects
- Sprint status workflow: Planning, Active, Completed
- Start date and end date tracking with validation
- Sprint backlog view showing all associated tickets
- Sprint velocity and progress indicators

#### Ticket Management
- Full CRUD operations for tickets with rich detail fields
- Ticket types: Bug, Feature, Task, Improvement, Epic
- Ticket priorities: Critical, High, Medium, Low
- Ticket statuses: Open, In Progress, In Review, QA Testing, Closed, Reopened
- Assignee and reporter tracking with user references
- Sprint and project association
- Due date tracking and overdue indicators
- Ticket detail pages with comments, time entries, and label display
- Ticket listing with multi-field filtering, sorting, and pagination

#### Kanban Board
- Interactive Kanban board view per project and sprint
- Columns representing ticket statuses with drag-and-drop support
- Visual ticket cards displaying priority, assignee, and type
- Real-time column counts and work-in-progress indicators
- Filtering by assignee, priority, and type within the board view

#### Labels
- Full CRUD operations for labels with name and color attributes
- Label assignment to tickets with many-to-many relationship
- Color-coded label display throughout the interface
- Label filtering on ticket listing pages

#### Comments
- Threaded comments on tickets with nested reply support
- Comment creation, editing, and deletion with ownership checks
- Markdown-compatible text content
- Timestamp display with relative time formatting

#### Time Entries
- Time logging on tickets with hours, description, and date fields
- Time entry creation, editing, and deletion with ownership checks
- Per-ticket time summary with total hours calculated
- Per-user time reports across projects and date ranges

#### Analytics Dashboard
- Project-level analytics with ticket distribution charts
- Ticket counts by status, priority, and type with visual breakdowns
- Sprint burndown and velocity metrics
- Team workload distribution showing tickets per assignee
- Overdue ticket tracking and summary statistics
- Department-level aggregate reporting for Super Admin and Project Manager roles

#### Audit Log
- Automatic logging of all create, update, and delete operations
- Audit entries capturing actor, action, entity type, entity ID, and timestamp
- Detailed change tracking with before and after values stored as JSON
- Audit log viewing interface with filters for entity type, action, actor, and date range
- Restricted access to audit logs based on user role

#### Database & Seeding
- SQLAlchemy 2.0 async models with full relationship mapping
- Alembic-compatible schema with proper foreign key constraints and indexes
- Database seeding script generating realistic sample data for all entities
- Seed data includes demo users across all roles, sample departments, projects, sprints, tickets, comments, labels, and time entries

#### Responsive UI
- Tailwind CSS responsive layout with mobile, tablet, and desktop breakpoints
- Collapsible sidebar navigation with role-aware menu items
- Consistent page layout with header, sidebar, and content area
- Jinja2 template inheritance with shared base template
- Flash message display for success, error, and informational notifications
- Form validation feedback with inline error messages
- Accessible HTML with semantic elements and ARIA attributes
- Dark-mode-ready utility class structure