IMPORTANT: 
uv run --env-file .env uvicorn main:app --reload --reload-dir .





Admin:
See: request from user
Expected to: 
identify possible subsets for multiple-choice categories
Source and convert images to urls
Store urls into textbox in website
Store into database after submit pressed
If submission is not/successful: banner of non/acknowledgement in website

Labeller:
See: 
Task_id
Multiple-choice categorisation of possible subsets
If image/audio/video URLs exist: rendered visuals/audio
Expected to: 
Set label[] within Task
output a category from choices given and label open-ended data
If submission is not/successful: banner of non/acknowledgement in website

CREATE TABLE `Job` (
	`job_id` text,
	`task_id` text,
	`completed_at` text,
	CONSTRAINT `Job_pk` PRIMARY KEY(`job_id`, `task_id`, `completed_at`)
);

CREATE TABLE `Task` (
	`task_id` text,
	`url` text,
	`client_id` text,
	`job_id` text,
	`labeller_id` text,
	`label` text,
	`categories` text,
	`status` text,
	`qc_label` text,
	CONSTRAINT `Task_pk` PRIMARY KEY(`task_id`, `url`, `client_id`, `job_id`, `labeller_id`, `label`, `categories`, `status`, `qc_label`)
);

CREATE TABLE `AI` (
	`job_id` text,
	`total_tasks` integer,
	CONSTRAINT `AI_pk` PRIMARY KEY(`job_id`, `total_tasks`)
);

in the backend python project i want to create unit tests for the labeller related flows. 
1. use a mocked db implementation for db calls to turso
2. propose happy, sad, edge cases 
3. unit tests only for now

write a plan first. no coding. keep responses minimal and short, sacrifice grammatical precisenss for concision.