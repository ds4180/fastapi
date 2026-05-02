--
-- PostgreSQL database dump
--

\restrict gaIXbyEruSpVJ7qbm4RUHIsNPnjissYbG8vISvKauuV1ghqhauUqaqHPop2XTk5

-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE ONLY public.user_session DROP CONSTRAINT user_session_user_id_fkey;
ALTER TABLE ONLY public.user_profiles DROP CONSTRAINT user_profiles_user_id_fkey;
ALTER TABLE ONLY public.service_engine DROP CONSTRAINT service_engine_registry_id_fkey;
ALTER TABLE ONLY public.service_app DROP CONSTRAINT service_app_engine_id_fkey;
ALTER TABLE ONLY public.question DROP CONSTRAINT question_user_id_fkey;
ALTER TABLE ONLY public.question_read_user DROP CONSTRAINT question_read_user_user_id_fkey;
ALTER TABLE ONLY public.question_read_user DROP CONSTRAINT question_read_user_question_id_fkey;
ALTER TABLE ONLY public.question_reaction DROP CONSTRAINT question_reaction_user_id_fkey;
ALTER TABLE ONLY public.question_reaction DROP CONSTRAINT question_reaction_question_id_fkey;
ALTER TABLE ONLY public.question_image DROP CONSTRAINT question_image_question_id_fkey;
ALTER TABLE ONLY public.push_subscription DROP CONSTRAINT push_subscription_user_id_fkey;
ALTER TABLE ONLY public.post DROP CONSTRAINT post_user_id_fkey;
ALTER TABLE ONLY public.post_tag DROP CONSTRAINT post_tag_tag_id_fkey;
ALTER TABLE ONLY public.post_tag DROP CONSTRAINT post_tag_post_id_fkey;
ALTER TABLE ONLY public.post_read DROP CONSTRAINT post_read_user_id_fkey;
ALTER TABLE ONLY public.post_read DROP CONSTRAINT post_read_post_id_fkey;
ALTER TABLE ONLY public.post_reaction DROP CONSTRAINT post_reaction_user_id_fkey;
ALTER TABLE ONLY public.post_reaction DROP CONSTRAINT post_reaction_post_id_fkey;
ALTER TABLE ONLY public.post DROP CONSTRAINT post_board_id_fkey;
ALTER TABLE ONLY public.menu DROP CONSTRAINT menu_parent_id_fkey;
ALTER TABLE ONLY public.menu DROP CONSTRAINT menu_app_id_fkey;
ALTER TABLE ONLY public.media_assets DROP CONSTRAINT media_assets_user_id_fkey;
ALTER TABLE ONLY public.dayoff DROP CONSTRAINT dayoff_user_id_fkey;
ALTER TABLE ONLY public.comment DROP CONSTRAINT comment_user_id_fkey;
ALTER TABLE ONLY public.comment DROP CONSTRAINT comment_post_id_fkey;
ALTER TABLE ONLY public.comment DROP CONSTRAINT comment_parent_id_fkey;
ALTER TABLE ONLY public.board_config DROP CONSTRAINT board_config_service_instance_id_fkey;
ALTER TABLE ONLY public.answer DROP CONSTRAINT answer_user_id_fkey;
ALTER TABLE ONLY public.answer DROP CONSTRAINT answer_question_id_fkey;
ALTER TABLE ONLY public.alert DROP CONSTRAINT alert_user_id_fkey;
DROP INDEX public.ix_user_session_status;
DROP INDEX public.ix_user_session_session_key;
DROP INDEX public.ix_user_session_login_at;
DROP INDEX public.ix_user_session_last_activity;
DROP INDEX public.ix_user_session_device_category;
DROP INDEX public.ix_system_config_key;
DROP INDEX public.ix_page_slug;
DROP INDEX public.ix_media_assets_user_id;
DROP INDEX public.ix_media_assets_target_id;
DROP INDEX public.ix_media_assets_is_deleted;
DROP INDEX public.ix_media_assets_app_id;
DROP INDEX public.ix_dayoff_user_date_active;
DROP INDEX public.ix_dayoff_group_id;
DROP INDEX public.ix_board_config_slug;
DROP INDEX public.ix_app_registry_app_id;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_username_key;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_pkey;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_email_key;
ALTER TABLE ONLY public.user_session DROP CONSTRAINT user_session_pkey;
ALTER TABLE ONLY public.user_profiles DROP CONSTRAINT user_profiles_pkey;
ALTER TABLE ONLY public.post_read DROP CONSTRAINT uq_user_post_read;
ALTER TABLE ONLY public.tag DROP CONSTRAINT tag_pkey;
ALTER TABLE ONLY public.tag DROP CONSTRAINT tag_name_key;
ALTER TABLE ONLY public.system_config DROP CONSTRAINT system_config_pkey;
ALTER TABLE ONLY public.service_registry DROP CONSTRAINT service_registry_pkey;
ALTER TABLE ONLY public.service_instance DROP CONSTRAINT service_instance_pkey;
ALTER TABLE ONLY public.service_engine DROP CONSTRAINT service_engine_pkey;
ALTER TABLE ONLY public.service_app DROP CONSTRAINT service_app_pkey;
ALTER TABLE ONLY public.question_read_user DROP CONSTRAINT question_read_user_pkey;
ALTER TABLE ONLY public.question_reaction DROP CONSTRAINT question_reaction_pkey;
ALTER TABLE ONLY public.question DROP CONSTRAINT question_pkey;
ALTER TABLE ONLY public.question_image DROP CONSTRAINT question_image_pkey;
ALTER TABLE ONLY public.push_subscription DROP CONSTRAINT push_subscription_pkey;
ALTER TABLE ONLY public.push_subscription DROP CONSTRAINT push_subscription_endpoint_key;
ALTER TABLE ONLY public.post_tag DROP CONSTRAINT post_tag_pkey;
ALTER TABLE ONLY public.post_read DROP CONSTRAINT post_read_pkey;
ALTER TABLE ONLY public.post_reaction DROP CONSTRAINT post_reaction_pkey;
ALTER TABLE ONLY public.post DROP CONSTRAINT post_pkey;
ALTER TABLE ONLY public.page DROP CONSTRAINT page_pkey;
ALTER TABLE ONLY public.menu DROP CONSTRAINT menu_pkey;
ALTER TABLE ONLY public.media_assets DROP CONSTRAINT media_assets_pkey;
ALTER TABLE ONLY public.dayoff DROP CONSTRAINT dayoff_pkey;
ALTER TABLE ONLY public.comment DROP CONSTRAINT comment_pkey;
ALTER TABLE ONLY public.board_config DROP CONSTRAINT board_config_pkey;
ALTER TABLE ONLY public.app_registry DROP CONSTRAINT app_registry_pkey;
ALTER TABLE ONLY public.answer DROP CONSTRAINT answer_pkey;
ALTER TABLE ONLY public.alert DROP CONSTRAINT alert_pkey;
ALTER TABLE ONLY public.alembic_version DROP CONSTRAINT alembic_version_pkc;
ALTER TABLE public.users ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.user_session ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.tag ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.service_instance ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.service_app ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.question_image ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.question ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.push_subscription ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.post_read ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.post ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.page ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.menu ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.media_assets ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.dayoff ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.comment ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.board_config ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.answer ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.alert ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE public.users_id_seq;
DROP TABLE public.users;
DROP SEQUENCE public.user_session_id_seq;
DROP TABLE public.user_session;
DROP TABLE public.user_profiles;
DROP SEQUENCE public.tag_id_seq;
DROP TABLE public.tag;
DROP TABLE public.system_config;
DROP TABLE public.service_registry;
DROP SEQUENCE public.service_instance_id_seq;
DROP TABLE public.service_instance;
DROP TABLE public.service_engine;
DROP SEQUENCE public.service_app_id_seq;
DROP TABLE public.service_app;
DROP TABLE public.question_read_user;
DROP TABLE public.question_reaction;
DROP SEQUENCE public.question_image_id_seq;
DROP TABLE public.question_image;
DROP SEQUENCE public.question_id_seq;
DROP TABLE public.question;
DROP SEQUENCE public.push_subscription_id_seq;
DROP TABLE public.push_subscription;
DROP TABLE public.post_tag;
DROP SEQUENCE public.post_read_id_seq;
DROP TABLE public.post_read;
DROP TABLE public.post_reaction;
DROP SEQUENCE public.post_id_seq;
DROP TABLE public.post;
DROP SEQUENCE public.page_id_seq;
DROP TABLE public.page;
DROP SEQUENCE public.menu_id_seq;
DROP TABLE public.menu;
DROP SEQUENCE public.media_assets_id_seq;
DROP TABLE public.media_assets;
DROP SEQUENCE public.dayoff_id_seq;
DROP TABLE public.dayoff;
DROP SEQUENCE public.comment_id_seq;
DROP TABLE public.comment;
DROP SEQUENCE public.board_config_id_seq;
DROP TABLE public.board_config;
DROP TABLE public.app_registry;
DROP SEQUENCE public.answer_id_seq;
DROP TABLE public.answer;
DROP SEQUENCE public.alert_id_seq;
DROP TABLE public.alert;
DROP TABLE public.alembic_version;
-- *not* dropping schema, since initdb creates it
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alert; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert (
    id integer NOT NULL,
    message text NOT NULL,
    level integer,
    style character varying,
    route character varying,
    redirect_url character varying,
    is_active boolean,
    start_date timestamp without time zone,
    end_date timestamp without time zone,
    create_date timestamp without time zone NOT NULL,
    user_id integer NOT NULL,
    "position" character varying,
    target_users character varying,
    confirm_text character varying,
    reset_sec integer
);


--
-- Name: alert_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alert_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alert_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alert_id_seq OWNED BY public.alert.id;


--
-- Name: answer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answer (
    id integer NOT NULL,
    content text NOT NULL,
    create_date timestamp without time zone NOT NULL,
    question_id integer,
    user_id integer NOT NULL
);


--
-- Name: answer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.answer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: answer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.answer_id_seq OWNED BY public.answer.id;


--
-- Name: app_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_registry (
    app_id character varying NOT NULL,
    name character varying NOT NULL,
    description text,
    frontend_route character varying,
    main_component character varying,
    config_schema jsonb,
    is_active boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    title character varying,
    app_type character varying DEFAULT 'INSTANCE'::character varying,
    icon_default character varying,
    min_read_rank integer DEFAULT 0,
    min_write_rank integer DEFAULT 2,
    admin_ids jsonb DEFAULT '[]'::jsonb
);


--
-- Name: board_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.board_config (
    id integer NOT NULL,
    slug character varying NOT NULL,
    name character varying NOT NULL,
    description character varying,
    layout_type character varying,
    items_per_page integer,
    fields_def jsonb,
    options jsonb,
    perm_read jsonb,
    perm_write jsonb,
    is_active boolean,
    create_date timestamp without time zone NOT NULL,
    service_instance_id integer
);


--
-- Name: board_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.board_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: board_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.board_config_id_seq OWNED BY public.board_config.id;


--
-- Name: comment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comment (
    id integer NOT NULL,
    post_id integer NOT NULL,
    user_id integer NOT NULL,
    parent_id integer,
    content text NOT NULL,
    create_date timestamp without time zone,
    modify_date timestamp without time zone
);


--
-- Name: comment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.comment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: comment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.comment_id_seq OWNED BY public.comment.id;


--
-- Name: dayoff; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dayoff (
    id integer NOT NULL,
    user_id integer NOT NULL,
    status character varying,
    date date NOT NULL,
    type character varying NOT NULL,
    memo text,
    create_date timestamp without time zone NOT NULL,
    group_id character varying,
    is_deleted boolean NOT NULL,
    delete_date timestamp without time zone
);


--
-- Name: dayoff_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dayoff_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dayoff_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dayoff_id_seq OWNED BY public.dayoff.id;


--
-- Name: media_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media_assets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    access_level character varying(20),
    app_id character varying(50),
    target_id character varying(100),
    original_name character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    thumbnail_path character varying(500),
    meta_info jsonb,
    file_size integer,
    mime_type character varying(100),
    category character varying(20),
    is_deleted boolean,
    created_at timestamp without time zone,
    deleted_at timestamp without time zone
);


--
-- Name: media_assets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.media_assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: media_assets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.media_assets_id_seq OWNED BY public.media_assets.id;


--
-- Name: menu; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.menu (
    id integer NOT NULL,
    parent_id integer,
    title character varying NOT NULL,
    icon_name character varying,
    icon_color character varying,
    link_type character varying,
    external_url character varying,
    "order" integer,
    is_visible boolean,
    min_rank integer,
    page_id integer,
    app_id character varying,
    app_instance_id integer
);


--
-- Name: menu_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.menu_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: menu_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.menu_id_seq OWNED BY public.menu.id;


--
-- Name: page; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.page (
    id integer NOT NULL,
    slug character varying NOT NULL,
    title character varying NOT NULL,
    content text,
    content_json jsonb NOT NULL,
    status character varying,
    min_rank integer,
    published_at timestamp without time zone NOT NULL,
    expired_at timestamp without time zone,
    view_count integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    is_deleted boolean NOT NULL,
    delete_date timestamp without time zone,
    is_active boolean,
    redirect_url character varying
);


--
-- Name: page_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.page_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: page_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.page_id_seq OWNED BY public.page.id;


--
-- Name: post; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.post (
    id integer NOT NULL,
    board_id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying NOT NULL,
    content_json jsonb NOT NULL,
    extra_data jsonb,
    status character varying,
    view_count integer,
    create_date timestamp without time zone,
    modify_date timestamp without time zone,
    content text,
    is_deleted boolean NOT NULL,
    delete_date timestamp without time zone
);


--
-- Name: post_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.post_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: post_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.post_id_seq OWNED BY public.post.id;


--
-- Name: post_reaction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.post_reaction (
    user_id integer NOT NULL,
    post_id integer NOT NULL,
    reaction_type character varying NOT NULL
);


--
-- Name: post_read; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.post_read (
    id integer NOT NULL,
    user_id integer NOT NULL,
    post_id integer NOT NULL,
    first_read_at timestamp without time zone,
    last_read_at timestamp without time zone,
    read_count integer,
    device_category character varying
);


--
-- Name: post_read_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.post_read_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: post_read_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.post_read_id_seq OWNED BY public.post_read.id;


--
-- Name: post_tag; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.post_tag (
    post_id integer NOT NULL,
    tag_id integer NOT NULL
);


--
-- Name: push_subscription; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.push_subscription (
    id integer NOT NULL,
    user_id integer NOT NULL,
    endpoint text NOT NULL,
    p256dh character varying NOT NULL,
    auth character varying NOT NULL
);


--
-- Name: push_subscription_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.push_subscription_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: push_subscription_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.push_subscription_id_seq OWNED BY public.push_subscription.id;


--
-- Name: question; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question (
    id integer NOT NULL,
    subject character varying NOT NULL,
    content text NOT NULL,
    create_date timestamp without time zone NOT NULL,
    user_id integer NOT NULL,
    modify_date timestamp without time zone,
    is_deleted boolean NOT NULL,
    delete_date timestamp without time zone
);


--
-- Name: question_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.question_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: question_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.question_id_seq OWNED BY public.question.id;


--
-- Name: question_image; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_image (
    id integer NOT NULL,
    filename character varying NOT NULL,
    original_name character varying NOT NULL,
    question_id integer,
    thumbnail_filename character varying
);


--
-- Name: question_image_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.question_image_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: question_image_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.question_image_id_seq OWNED BY public.question_image.id;


--
-- Name: question_reaction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_reaction (
    user_id integer NOT NULL,
    question_id integer NOT NULL,
    reaction_type character varying NOT NULL
);


--
-- Name: question_read_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_read_user (
    user_id integer NOT NULL,
    question_id integer NOT NULL
);


--
-- Name: service_app; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_app (
    id integer NOT NULL,
    name character varying NOT NULL,
    engine_id character varying NOT NULL,
    config jsonb,
    is_active boolean,
    created_at timestamp without time zone
);


--
-- Name: service_app_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_app_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_app_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_app_id_seq OWNED BY public.service_app.id;


--
-- Name: service_engine; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_engine (
    id character varying NOT NULL,
    registry_id character varying NOT NULL,
    version character varying NOT NULL,
    frontend_plugin character varying,
    config_schema jsonb,
    is_active boolean,
    created_at timestamp without time zone
);


--
-- Name: service_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_instance (
    id integer NOT NULL,
    name character varying NOT NULL,
    is_active boolean,
    created_at timestamp without time zone,
    service_app_ids jsonb
);


--
-- Name: service_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_instance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_instance_id_seq OWNED BY public.service_instance.id;


--
-- Name: service_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_registry (
    id character varying NOT NULL,
    name character varying NOT NULL,
    description text
);


--
-- Name: system_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_config (
    key character varying NOT NULL,
    value jsonb NOT NULL,
    description character varying,
    updated_date timestamp without time zone
);


--
-- Name: tag; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag (
    id integer NOT NULL,
    name character varying NOT NULL,
    color character varying
);


--
-- Name: tag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tag_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tag_id_seq OWNED BY public.tag.id;


--
-- Name: user_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_profiles (
    user_id integer NOT NULL,
    rank_level integer,
    is_active boolean,
    employee_no character varying,
    resident_no character varying,
    joined_date date,
    bank_name character varying,
    account_no character varying,
    admin_memo text
);


--
-- Name: user_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_session (
    id integer NOT NULL,
    user_id integer NOT NULL,
    session_key character varying NOT NULL,
    device_category character varying NOT NULL,
    status character varying,
    device_name character varying,
    ip_address character varying,
    login_at timestamp without time zone,
    logout_at timestamp without time zone,
    last_activity timestamp without time zone
);


--
-- Name: user_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_session_id_seq OWNED BY public.user_session.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying NOT NULL,
    password character varying NOT NULL,
    email character varying NOT NULL,
    real_name character varying,
    phone character varying
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: alert id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert ALTER COLUMN id SET DEFAULT nextval('public.alert_id_seq'::regclass);


--
-- Name: answer id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer ALTER COLUMN id SET DEFAULT nextval('public.answer_id_seq'::regclass);


--
-- Name: board_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_config ALTER COLUMN id SET DEFAULT nextval('public.board_config_id_seq'::regclass);


--
-- Name: comment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment ALTER COLUMN id SET DEFAULT nextval('public.comment_id_seq'::regclass);


--
-- Name: dayoff id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dayoff ALTER COLUMN id SET DEFAULT nextval('public.dayoff_id_seq'::regclass);


--
-- Name: media_assets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets ALTER COLUMN id SET DEFAULT nextval('public.media_assets_id_seq'::regclass);


--
-- Name: menu id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.menu ALTER COLUMN id SET DEFAULT nextval('public.menu_id_seq'::regclass);


--
-- Name: page id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page ALTER COLUMN id SET DEFAULT nextval('public.page_id_seq'::regclass);


--
-- Name: post id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post ALTER COLUMN id SET DEFAULT nextval('public.post_id_seq'::regclass);


--
-- Name: post_read id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_read ALTER COLUMN id SET DEFAULT nextval('public.post_read_id_seq'::regclass);


--
-- Name: push_subscription id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscription ALTER COLUMN id SET DEFAULT nextval('public.push_subscription_id_seq'::regclass);


--
-- Name: question id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question ALTER COLUMN id SET DEFAULT nextval('public.question_id_seq'::regclass);


--
-- Name: question_image id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_image ALTER COLUMN id SET DEFAULT nextval('public.question_image_id_seq'::regclass);


--
-- Name: service_app id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_app ALTER COLUMN id SET DEFAULT nextval('public.service_app_id_seq'::regclass);


--
-- Name: service_instance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_instance ALTER COLUMN id SET DEFAULT nextval('public.service_instance_id_seq'::regclass);


--
-- Name: tag id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag ALTER COLUMN id SET DEFAULT nextval('public.tag_id_seq'::regclass);


--
-- Name: user_session id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_session ALTER COLUMN id SET DEFAULT nextval('public.user_session_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
2013b0dbd1a4
\.


--
-- Data for Name: alert; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alert (id, message, level, style, route, redirect_url, is_active, start_date, end_date, create_date, user_id, "position", target_users, confirm_text, reset_sec) FROM stdin;
\.


--
-- Data for Name: answer; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.answer (id, content, create_date, question_id, user_id) FROM stdin;
\.


--
-- Data for Name: app_registry; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.app_registry (app_id, name, description, frontend_route, main_component, config_schema, is_active, created_at, updated_at, title, app_type, icon_default, min_read_rank, min_write_rank, admin_ids) FROM stdin;
board	게시판엔진	기본 게시판엔진입니다. 게시판엔진 설정에서 인스턴트 생성 후 게시판으로 사용합니다.	/v1/app/board/[slug]	BoardEngine	{"instance_info": {"model_name": "BoardConfig", "placeholder": "[slug]", "lookup_field": "id", "return_field": "slug"}}	t	2026-03-03 17:32:18.324802	2026-03-18 15:22:58.555109	게시판엔진	INSTANCE	\N	0	2	[]
page	페이지엔진	page를 생성하고 관리 합니다. 	/v1/custom/page/[slug]	PageEngine	{"instance_info": {"id_field": "id", "model_name": "Page", "slug_field": "slug", "display_field": "title"}}	t	2026-03-12 14:48:44.148256	2026-03-18 17:18:01.922506	페이지엔진	STATIC	box	0	2	[]
dayoff	결근계	결근계를 작성합니다. 	/v1/custom/dayoff		{}	t	2026-03-11 19:59:45.782188	2026-04-09 12:31:04.950631	결근계	STATIC	box	2	2	[]
\.


--
-- Data for Name: board_config; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.board_config (id, slug, name, description, layout_type, items_per_page, fields_def, options, perm_read, perm_write, is_active, create_date, service_instance_id) FROM stdin;
2	field	필드		list	10	[{"name": "hp", "type": "text", "label": "연락처", "description": "전화번호만."}]	{"use_file": true, "use_secret": false, "editor_type": "field", "use_comment": true, "use_thumbnail": false}	{"ROLE_GUEST": "GLOBAL"}	{"ROLE_USER": "GLOBAL"}	t	2026-03-03 17:13:51.775282	\N
4	test	동적폼 테스트		list	10	[{"key": "df-1", "type": "text", "label": "df-1", "required": false, "placeholder": ""}, {"key": "df-2", "type": "number", "label": "df-2 ", "required": false, "placeholder": ""}, {"key": "df-3", "type": "date", "label": "df-3", "required": false, "placeholder": ""}, {"key": "df-4", "type": "select", "label": "df-4", "required": false, "placeholder": ""}]	{}	{"ROLE_GUEST": "GLOBAL"}	{"ROLE_USER": "GLOBAL"}	t	2026-04-09 21:23:43.082248	\N
3	free	자유	자유게시판 	list	10	[]	{}	{"ROLE_GUEST": "GLOBAL"}	{"ROLE_USER": "GLOBAL"}	t	2026-04-03 15:06:43.076537	1
1	notice	공지		list	10	[]	{"use_file": true, "use_secret": false, "editor_type": "tiptap", "form_schema": [], "use_comment": true, "use_thumbnail": false}	{"ROLE_GUEST": "GLOBAL"}	{"ROLE_USER": "GLOBAL"}	t	2026-03-03 17:02:34.878696	1
\.


--
-- Data for Name: comment; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.comment (id, post_id, user_id, parent_id, content, create_date, modify_date) FROM stdin;
\.


--
-- Data for Name: dayoff; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dayoff (id, user_id, status, date, type, memo, create_date, group_id, is_deleted, delete_date) FROM stdin;
39	1	REQUESTED	2026-04-22	ANNUAL		2026-04-03 14:01:37.8612	20260422-20260429	t	2026-04-03 14:03:42.509714
40	1	REQUESTED	2026-04-23	ANNUAL		2026-04-03 14:01:37.861958	20260422-20260429	t	2026-04-03 14:03:42.509714
3	1	REQUESTED	2026-03-26	ANNUAL		2026-03-06 17:08:19.168463	\N	t	2026-03-06 17:38:27.62837
4	1	REQUESTED	2026-03-27	ANNUAL		2026-03-06 17:08:19.169161	\N	t	2026-03-06 17:38:30.568919
5	1	REQUESTED	2026-03-28	ANNUAL		2026-03-06 17:08:19.169775	\N	t	2026-03-06 17:38:33.845314
13	1	REQUESTED	2026-03-27	ANNUAL		2026-03-06 17:43:07.156646	20260327-20260330	t	2026-03-06 17:44:19.346944
14	1	REQUESTED	2026-03-28	ANNUAL		2026-03-06 17:43:07.157392	20260327-20260330	t	2026-03-06 17:44:19.346944
15	1	REQUESTED	2026-03-29	ANNUAL		2026-03-06 17:43:07.158047	20260327-20260330	t	2026-03-06 17:44:19.346944
16	1	REQUESTED	2026-03-30	ANNUAL		2026-03-06 17:43:07.158643	20260327-20260330	t	2026-03-06 17:44:19.346944
6	1	REQUESTED	2026-03-14	ANNUAL		2026-03-06 17:39:53.777297	20260314-20260316	t	2026-03-06 17:44:22.363156
7	1	REQUESTED	2026-03-15	ANNUAL		2026-03-06 17:39:53.778145	20260314-20260316	t	2026-03-06 17:44:22.363156
8	1	REQUESTED	2026-03-16	ANNUAL		2026-03-06 17:39:53.77881	20260314-20260316	t	2026-03-06 17:44:22.363156
32	1	REQUESTED	2026-07-03	ANNUAL		2026-03-11 20:00:52.088632	20260703-20260705	t	2026-03-14 22:15:15.491852
33	1	REQUESTED	2026-07-04	ANNUAL		2026-03-11 20:00:52.08996	20260703-20260705	t	2026-03-14 22:15:15.491852
34	1	REQUESTED	2026-07-05	ANNUAL		2026-03-11 20:00:52.090951	20260703-20260705	t	2026-03-14 22:15:15.491852
28	1	REQUESTED	2026-04-02	ANNUAL		2026-03-11 19:52:53.948185	20260402-20260403	t	2026-03-14 22:15:18.315681
29	1	REQUESTED	2026-04-03	ANNUAL		2026-03-11 19:52:53.949375	20260402-20260403	t	2026-03-14 22:15:18.315681
17	1	REQUESTED	2026-03-25	ANNUAL		2026-03-06 17:44:31.2255	20260325-20260327	t	2026-03-14 22:15:22.569288
18	1	REQUESTED	2026-03-26	ANNUAL		2026-03-06 17:44:31.226773	20260325-20260327	t	2026-03-14 22:15:22.569288
19	1	REQUESTED	2026-03-27	ANNUAL		2026-03-06 17:44:31.227457	20260325-20260327	t	2026-03-14 22:15:22.569288
30	1	REQUESTED	2026-03-12	ANNUAL		2026-03-11 19:57:08.000733	20260312-20260313	t	2026-03-14 22:15:29.271493
31	1	REQUESTED	2026-03-13	ANNUAL		2026-03-11 19:57:08.002057	20260312-20260313	t	2026-03-14 22:15:29.271493
20	3	REQUESTED	2026-03-16	OFFICIAL		2026-03-06 17:45:13.103637	20260316-20260319	t	2026-03-18 14:39:29.350766
21	3	REQUESTED	2026-03-17	OFFICIAL		2026-03-06 17:45:13.104302	20260316-20260319	t	2026-03-18 14:39:29.350766
22	3	REQUESTED	2026-03-18	OFFICIAL		2026-03-06 17:45:13.104877	20260316-20260319	t	2026-03-18 14:39:29.350766
23	3	REQUESTED	2026-03-19	OFFICIAL		2026-03-06 17:45:13.105476	20260316-20260319	t	2026-03-18 14:39:29.350766
37	3	REQUESTED	2026-03-27	ANNUAL		2026-03-15 18:48:22.709797	20260327-20260328	t	2026-03-18 14:39:33.003507
38	3	REQUESTED	2026-03-28	ANNUAL		2026-03-15 18:48:22.710806	20260327-20260328	t	2026-03-18 14:39:33.003507
41	1	REQUESTED	2026-04-24	ANNUAL		2026-04-03 14:01:37.862587	20260422-20260429	t	2026-04-03 14:03:42.509714
42	1	REQUESTED	2026-04-25	ANNUAL		2026-04-03 14:01:37.863175	20260422-20260429	t	2026-04-03 14:03:42.509714
43	1	REQUESTED	2026-04-26	ANNUAL		2026-04-03 14:01:37.863735	20260422-20260429	t	2026-04-03 14:03:42.509714
44	1	REQUESTED	2026-04-27	ANNUAL		2026-04-03 14:01:37.864421	20260422-20260429	t	2026-04-03 14:03:42.509714
45	1	REQUESTED	2026-04-28	ANNUAL		2026-04-03 14:01:37.864943	20260422-20260429	t	2026-04-03 14:03:42.509714
46	1	REQUESTED	2026-04-29	ANNUAL		2026-04-03 14:01:37.865479	20260422-20260429	t	2026-04-03 14:03:42.509714
35	1	REQUESTED	2026-03-31	ANNUAL		2026-03-15 10:21:11.632766	20260331-20260401	t	2026-04-03 14:11:14.396827
36	1	REQUESTED	2026-04-01	ANNUAL		2026-03-15 10:21:11.634771	20260331-20260401	t	2026-04-03 14:11:14.396827
25	5	REJECTED	2026-03-26	ANNUAL		2026-03-06 17:55:08.184997	20260325-20260326	f	\N
50	1	REQUESTED	2026-04-16	ANNUAL		2026-04-03 14:21:06.574478	20260416-20260417	t	2026-04-03 14:22:37.775777
51	1	REQUESTED	2026-04-17	ANNUAL		2026-04-03 14:21:06.574949	20260416-20260417	t	2026-04-03 14:22:37.775777
47	1	REQUESTED	2026-04-30	ANNUAL		2026-04-03 14:02:37.942981	20260429-20260430	t	2026-04-03 14:24:25.878136
48	1	REQUESTED	2026-04-29	ANNUAL		2026-04-03 14:04:59.99191	20260429-20260430	t	2026-04-03 14:24:25.878136
49	1	REQUESTED	2026-04-30	ANNUAL		2026-04-03 14:04:59.992623	20260429-20260430	t	2026-04-03 14:24:25.878136
52	1	REQUESTED	2026-04-29	ANNUAL		2026-04-03 14:24:21.118475	20260429-20260430	t	2026-04-03 14:24:25.878136
53	1	REQUESTED	2026-04-30	ANNUAL		2026-04-03 14:24:21.119135	20260429-20260430	t	2026-04-03 14:24:25.878136
54	1	REJECTED	2026-04-09	ANNUAL		2026-04-06 18:57:39.248939	20260409-20260411	f	\N
55	1	REJECTED	2026-04-10	ANNUAL		2026-04-06 18:57:39.251145	20260409-20260411	f	\N
56	1	REJECTED	2026-04-11	ANNUAL		2026-04-06 18:57:39.252439	20260409-20260411	f	\N
26	4	REJECTED	2026-03-17	ANNUAL		2026-03-06 18:17:56.199189	20260317-20260318	f	\N
27	4	REJECTED	2026-03-18	ANNUAL		2026-03-06 18:17:56.200225	20260317-20260318	f	\N
24	5	REJECTED	2026-03-25	ANNUAL		2026-03-06 17:55:08.184048	20260325-20260326	f	\N
\.


--
-- Data for Name: media_assets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.media_assets (id, user_id, access_level, app_id, target_id, original_name, file_path, thumbnail_path, meta_info, file_size, mime_type, category, is_deleted, created_at, deleted_at) FROM stdin;
12	1	PUBLIC	general	\N	fall-8404115_1920.jpg	public/image/2026/04/11/6c407941-9f51-4a19-b914-116f3f7f5398.jpg	public/image/2026/04/11/thumbnails/6c407941-9f51-4a19-b914-116f3f7f5398_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/6c407941-9f51-4a19-b914-116f3f7f5398_lg.webp", "md": "public/image/2026/04/11/thumbnails/6c407941-9f51-4a19-b914-116f3f7f5398_md.webp", "sm": "public/image/2026/04/11/thumbnails/6c407941-9f51-4a19-b914-116f3f7f5398_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	t	2026-04-11 11:13:04.062149	2026-04-11 11:14:11.485347
11	1	PUBLIC	general	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/1b2f609c-9f1a-44cd-ac71-c0b7faa2fddb.jpg	public/image/2026/04/11/thumbnails/1b2f609c-9f1a-44cd-ac71-c0b7faa2fddb_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/1b2f609c-9f1a-44cd-ac71-c0b7faa2fddb_lg.webp", "md": "public/image/2026/04/11/thumbnails/1b2f609c-9f1a-44cd-ac71-c0b7faa2fddb_md.webp", "sm": "public/image/2026/04/11/thumbnails/1b2f609c-9f1a-44cd-ac71-c0b7faa2fddb_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 11:10:30.868206	2026-04-11 11:14:17.522138
10	1	PUBLIC	general	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/9fb3fc90-272f-41ab-bb98-a2df375d297a.jpg	public/image/2026/04/11/thumbnails/9fb3fc90-272f-41ab-bb98-a2df375d297a_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/9fb3fc90-272f-41ab-bb98-a2df375d297a_lg.webp", "md": "public/image/2026/04/11/thumbnails/9fb3fc90-272f-41ab-bb98-a2df375d297a_md.webp", "sm": "public/image/2026/04/11/thumbnails/9fb3fc90-272f-41ab-bb98-a2df375d297a_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 11:10:14.092644	2026-04-11 11:14:27.095046
9	1	PUBLIC	general	\N	fall-8404115_1920.jpg	public/image/2026/04/11/8249b11f-779d-421d-a942-3d361f593002.jpg	public/image/2026/04/11/thumbnails/8249b11f-779d-421d-a942-3d361f593002_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/8249b11f-779d-421d-a942-3d361f593002_lg.webp", "md": "public/image/2026/04/11/thumbnails/8249b11f-779d-421d-a942-3d361f593002_md.webp", "sm": "public/image/2026/04/11/thumbnails/8249b11f-779d-421d-a942-3d361f593002_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	t	2026-04-11 11:09:00.973235	2026-04-11 11:16:03.30759
7	1	PUBLIC	general	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/c87d14fd-5605-4f45-94b8-40ea067492bd.jpg	public/image/2026/04/11/thumbnails/c87d14fd-5605-4f45-94b8-40ea067492bd_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/c87d14fd-5605-4f45-94b8-40ea067492bd_lg.webp", "md": "public/image/2026/04/11/thumbnails/c87d14fd-5605-4f45-94b8-40ea067492bd_md.webp", "sm": "public/image/2026/04/11/thumbnails/c87d14fd-5605-4f45-94b8-40ea067492bd_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 11:06:43.64592	2026-04-11 11:16:12.21055
6	1	PUBLIC	general	\N	29a69eeb-35a5-489f-9256-53967ac8049a.jpg	public/image/2026/04/11/a6b31a13-c02b-4993-a214-06b73d0be42a.jpg	public/image/2026/04/11/thumbnails/a6b31a13-c02b-4993-a214-06b73d0be42a_md.webp	{"width": 4000, "height": 2252, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/a6b31a13-c02b-4993-a214-06b73d0be42a_lg.webp", "md": "public/image/2026/04/11/thumbnails/a6b31a13-c02b-4993-a214-06b73d0be42a_md.webp", "sm": "public/image/2026/04/11/thumbnails/a6b31a13-c02b-4993-a214-06b73d0be42a_sm.webp"}, "original_name": "29a69eeb-35a5-489f-9256-53967ac8049a.jpg"}	3193613	image/jpeg	image	t	2026-04-11 11:05:44.89103	2026-04-11 11:16:16.051112
5	1	PUBLIC	general	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/63608e77-4010-4cdf-a49a-a5931d655c39.jpg	public/image/2026/04/11/thumbnails/63608e77-4010-4cdf-a49a-a5931d655c39_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/63608e77-4010-4cdf-a49a-a5931d655c39_lg.webp", "md": "public/image/2026/04/11/thumbnails/63608e77-4010-4cdf-a49a-a5931d655c39_md.webp", "sm": "public/image/2026/04/11/thumbnails/63608e77-4010-4cdf-a49a-a5931d655c39_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 11:02:45.360348	2026-04-11 11:16:19.512939
4	1	PUBLIC	admin	\N	fall-8404115_1920.jpg	public/image/2026/04/11/d66adb2d-0c78-4c3f-bc2e-bab0aa187f12.jpg	public/image/2026/04/11/thumbnails/d66adb2d-0c78-4c3f-bc2e-bab0aa187f12_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/d66adb2d-0c78-4c3f-bc2e-bab0aa187f12_lg.webp", "md": "public/image/2026/04/11/thumbnails/d66adb2d-0c78-4c3f-bc2e-bab0aa187f12_md.webp", "sm": "public/image/2026/04/11/thumbnails/d66adb2d-0c78-4c3f-bc2e-bab0aa187f12_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	t	2026-04-11 11:02:04.814531	2026-04-11 11:16:22.864092
3	1	PUBLIC	admin	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/b4575d9d-aac3-4df4-b366-d625c98d43ea.jpg	public/image/2026/04/11/thumbnails/b4575d9d-aac3-4df4-b366-d625c98d43ea_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/b4575d9d-aac3-4df4-b366-d625c98d43ea_lg.webp", "md": "public/image/2026/04/11/thumbnails/b4575d9d-aac3-4df4-b366-d625c98d43ea_md.webp", "sm": "public/image/2026/04/11/thumbnails/b4575d9d-aac3-4df4-b366-d625c98d43ea_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 10:59:20.563944	2026-04-11 11:16:26.038447
2	1	PUBLIC	admin	\N	SRP-350352plusAC_user_한국어_Rev_1_11.pdf	public/document/2026/04/11/d8a7bf41-acb7-401d-a71d-0d465e6a4e71.pdf	\N	{"original_name": "SRP-350352plusAC_user_한국어_Rev_1_11.pdf"}	1246559	application/pdf	document	t	2026-04-11 10:56:13.14404	2026-04-11 11:16:29.008076
1	1	PUBLIC	admin	\N	4d641278-5b1f-4f7b-ad5d-f82907a85232.jpg	public/image/2026/04/11/3572c1c6-05b9-4875-b7e0-318b6a7f9b1d.jpg	public/image/2026/04/11/thumbnails/3572c1c6-05b9-4875-b7e0-318b6a7f9b1d_md.webp	{"width": 4000, "height": 2252, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/3572c1c6-05b9-4875-b7e0-318b6a7f9b1d_lg.webp", "md": "public/image/2026/04/11/thumbnails/3572c1c6-05b9-4875-b7e0-318b6a7f9b1d_md.webp", "sm": "public/image/2026/04/11/thumbnails/3572c1c6-05b9-4875-b7e0-318b6a7f9b1d_sm.webp"}, "original_name": "4d641278-5b1f-4f7b-ad5d-f82907a85232.jpg"}	3097147	image/jpeg	image	t	2026-04-11 10:55:19.925061	2026-04-11 11:16:33.391424
8	1	PUBLIC	general	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/0ec67849-6869-41be-acd2-93d342077bc5.jpg	public/image/2026/04/11/thumbnails/0ec67849-6869-41be-acd2-93d342077bc5_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/0ec67849-6869-41be-acd2-93d342077bc5_lg.webp", "md": "public/image/2026/04/11/thumbnails/0ec67849-6869-41be-acd2-93d342077bc5_md.webp", "sm": "public/image/2026/04/11/thumbnails/0ec67849-6869-41be-acd2-93d342077bc5_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-11 11:07:25.804875	2026-04-11 11:16:07.90914
13	1	PUBLIC	admin	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/11/86b6c230-289a-4688-9a19-4337e1cae7d9.jpg	public/image/2026/04/11/thumbnails/86b6c230-289a-4688-9a19-4337e1cae7d9_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/86b6c230-289a-4688-9a19-4337e1cae7d9_lg.webp", "md": "public/image/2026/04/11/thumbnails/86b6c230-289a-4688-9a19-4337e1cae7d9_md.webp", "sm": "public/image/2026/04/11/thumbnails/86b6c230-289a-4688-9a19-4337e1cae7d9_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	f	2026-04-11 11:51:23.615823	\N
14	1	PUBLIC	admin	\N	fall-8404115_1920.jpg	public/image/2026/04/11/4f972d06-3d3f-46a8-b165-7b950ce83fe3.jpg	public/image/2026/04/11/thumbnails/4f972d06-3d3f-46a8-b165-7b950ce83fe3_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "public/image/2026/04/11/thumbnails/4f972d06-3d3f-46a8-b165-7b950ce83fe3_lg.webp", "md": "public/image/2026/04/11/thumbnails/4f972d06-3d3f-46a8-b165-7b950ce83fe3_md.webp", "sm": "public/image/2026/04/11/thumbnails/4f972d06-3d3f-46a8-b165-7b950ce83fe3_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	f	2026-04-11 11:52:38.871643	\N
15	1	PUBLIC	admin	\N	SRP-350352plusAC_user_한국어_Rev_1_11.pdf	public/document/2026/04/17/0a9c6348-9c1a-4227-b16d-8df6b6bd7fc7.pdf	\N	{"original_name": "SRP-350352plusAC_user_한국어_Rev_1_11.pdf"}	1246559	application/pdf	document	f	2026-04-17 08:30:51.350547	\N
16	1	PUBLIC	admin	\N	shs.txt	public/document/2026/04/17/9f68b862-df95-4b94-9149-96efc568c694.txt	\N	{"original_name": "shs.txt"}	340	text/plain	document	f	2026-04-17 08:31:55.245302	\N
17	1	PUBLIC	admin	\N	fall-8404115_1920.jpg	public/image/2026/04/17/9a9479f6-860d-4dbd-9fc0-46ca1839f191.jpg	public/image/2026/04/17/thumbnails/9a9479f6-860d-4dbd-9fc0-46ca1839f191_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "public/image/2026/04/17/thumbnails/9a9479f6-860d-4dbd-9fc0-46ca1839f191_lg.webp", "md": "public/image/2026/04/17/thumbnails/9a9479f6-860d-4dbd-9fc0-46ca1839f191_md.webp", "sm": "public/image/2026/04/17/thumbnails/9a9479f6-860d-4dbd-9fc0-46ca1839f191_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	f	2026-04-17 11:55:19.829658	\N
18	1	PUBLIC	admin	\N	pumpkin-9830952_1280.jpg	public/image/2026/04/17/56042793-5806-4e9a-8fb2-9bc322882a8f.jpg	public/image/2026/04/17/thumbnails/56042793-5806-4e9a-8fb2-9bc322882a8f_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "public/image/2026/04/17/thumbnails/56042793-5806-4e9a-8fb2-9bc322882a8f_lg.webp", "md": "public/image/2026/04/17/thumbnails/56042793-5806-4e9a-8fb2-9bc322882a8f_md.webp", "sm": "public/image/2026/04/17/thumbnails/56042793-5806-4e9a-8fb2-9bc322882a8f_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	f	2026-04-17 11:56:14.534541	\N
21	1	PRIVATE	admin	\N	SRP-350352plusAC_user_한국어_Rev_1_11.pdf	private/users/1/58ee9ac7-e55d-472c-ab24-944bba131f46.pdf	\N	{"original_name": "SRP-350352plusAC_user_한국어_Rev_1_11.pdf"}	1246559	application/pdf	document	f	2026-04-17 12:05:32.379162	\N
20	1	SYSTEM	admin	\N	pumpkin-9830952_1280.jpg	system/global/office/2d9306d9-bb77-4489-bb3a-7d7d41d50bfc.jpg	system/global/office/thumbnails/2d9306d9-bb77-4489-bb3a-7d7d41d50bfc_md.webp	{"width": 1280, "height": 853, "thumbs": {"lg": "system/global/office/thumbnails/2d9306d9-bb77-4489-bb3a-7d7d41d50bfc_lg.webp", "md": "system/global/office/thumbnails/2d9306d9-bb77-4489-bb3a-7d7d41d50bfc_md.webp", "sm": "system/global/office/thumbnails/2d9306d9-bb77-4489-bb3a-7d7d41d50bfc_sm.webp"}, "original_name": "pumpkin-9830952_1280.jpg"}	214548	image/jpeg	image	t	2026-04-17 12:04:55.062147	2026-04-17 13:00:31.473073
19	1	SYSTEM	admin	\N	fall-8404115_1920.jpg	system/global/office/b5e54dcf-a6eb-4bab-93ac-b19a5af1ea0e.jpg	system/global/office/thumbnails/b5e54dcf-a6eb-4bab-93ac-b19a5af1ea0e_md.webp	{"width": 1440, "height": 1920, "thumbs": {"lg": "system/global/office/thumbnails/b5e54dcf-a6eb-4bab-93ac-b19a5af1ea0e_lg.webp", "md": "system/global/office/thumbnails/b5e54dcf-a6eb-4bab-93ac-b19a5af1ea0e_md.webp", "sm": "system/global/office/thumbnails/b5e54dcf-a6eb-4bab-93ac-b19a5af1ea0e_sm.webp"}, "original_name": "fall-8404115_1920.jpg"}	1751947	image/jpeg	image	t	2026-04-17 12:04:55.062139	2026-04-17 13:00:31.483306
\.


--
-- Data for Name: menu; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.menu (id, parent_id, title, icon_name, icon_color, link_type, external_url, "order", is_visible, min_rank, page_id, app_id, app_instance_id) FROM stdin;
5	\N	🛠️ 관리자 설정	\N	\N	URL	/v1/admin	99	t	3	\N	\N	\N
26	6	결근계 관리	🚀	\N	CUSTOM	/v1/admin/dayoff	0	t	2	\N	dayoff	-1
22	6	고정페이지리스트	bi:link-45deg	#666666	URL	/v1/admin/pages	0	t	1	\N	\N	-1
35	\N	결근계	🚀	\N	CUSTOM	\N	0	t	0	\N	dayoff	\N
33	\N	공지게시판	🚀	\N	APP	/v1/app/board/1	0	t	0	\N	board	1
12	6	접속기록	\N	\N	URL	/v1/admin/sessions	0	t	4	\N	\N	\N
18	6	페이지엔진	bi-link	#666666	APP	/v1/admin/page	0	t	0	\N	page	-1
23	\N	202	🚀	\N	URL	/v1/pages/sgv4	0	t	0	\N	\N	\N
6	\N	관리	\N	\N	FOLDER	/v1/admin	98	t	1	\N	\N	\N
20	6	게시판엔진	bi:link-45deg	#666666	URL	/v1/admin/apps/board/instances	0	t	0	\N	\N	-1
36	6	푸시알림	🚀	\N	URL	/v1/admin/pushs	0	t	0	\N	\N	\N
11	6	알림	\N	\N	URL	/v1/admin/alerts	0	t	3	\N	\N	\N
28	\N	canvas	🚀	\N	URL	/v1/custom/canvas	0	t	0	\N	\N	\N
27	\N	차트	🚀	\N	URL	/v1/custom/chart	0	t	0	\N	\N	\N
37	6	그룹관리	🚀	\N	URL	/v1/admin/group-manage	0	t	0	\N	\N	\N
\.


--
-- Data for Name: page; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.page (id, slug, title, content, content_json, status, min_rank, published_at, expired_at, view_count, created_at, updated_at, is_deleted, delete_date, is_active, redirect_url) FROM stdin;
1	test	첫번째두번째세번째	<p>dfdvvvvdd</p>	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "dfdvvvvdd", "type": "text"}]}]}	PUBLISHED	0	2026-03-12 09:00:00	\N	23	2026-03-12 14:59:42.832674	2026-04-10 21:17:10.281968	f	\N	t	\N
2	test2	test2	<h2><span style="color: rgb(195, 34, 34);"><s>이제야 되는 듯 하다.  </s></span></h2><h2><span style="color: rgb(0, 0, 0);"><strong>ㅇㄹ</strong></span></h2><p></p>	{"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2, "textAlign": null}, "content": [{"text": "이제야 되는 듯 하다.  ", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "#c32222"}}, {"type": "strike"}]}]}, {"type": "heading", "attrs": {"level": 2, "textAlign": null}, "content": [{"text": "ㅇㄹ", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "#000000"}}, {"type": "bold"}]}]}, {"type": "paragraph", "attrs": {"textAlign": null}}]}	PUBLISHED	0	2026-03-12 09:00:00	\N	103	2026-03-12 16:36:21.100299	2026-04-09 23:21:59.429454	f	\N	t	\N
3	20260401notice	페이지 앱 복원	<p><span style="font-size: 48px; color: rgb(0, 0, 0);">이거 기본 색은 왜 <mark data-color="#b2f2bb" style="background-color: rgb(178, 242, 187); color: inherit;">흰색</mark>인가?</span></p><p><span style="font-size: 48px; color: rgb(0, 0, 0);">커서도 왜 <mark data-color="#a5d8ff" style="background-color: rgb(165, 216, 255); color: inherit;">흰색</mark>인가?</span></p><p></p><h1><span style="font-size: 48px; color: rgb(0, 0, 0);">h1 크기 확인</span></h1><h2><span style="color: rgb(0, 0, 0);">h2크기</span></h2><h3><span style="color: rgb(0, 0, 0);">h3</span></h3><p></p>	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "이거 기본 색은 왜 ", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}]}, {"text": "흰색", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}, {"type": "highlight", "attrs": {"color": "#b2f2bb"}}]}, {"text": "인가?", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}]}]}, {"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "커서도 왜 ", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}]}, {"text": "흰색", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}, {"type": "highlight", "attrs": {"color": "#a5d8ff"}}]}, {"text": "인가?", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}]}]}, {"type": "paragraph", "attrs": {"textAlign": null}}, {"type": "heading", "attrs": {"level": 1, "textAlign": null}, "content": [{"text": "h1 크기 확인", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "rgb(0, 0, 0)", "fontSize": "48px"}}]}]}, {"type": "heading", "attrs": {"level": 2, "textAlign": null}, "content": [{"text": "h2크기", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "#000000", "fontSize": null}}]}]}, {"type": "heading", "attrs": {"level": 3, "textAlign": null}, "content": [{"text": "h3", "type": "text", "marks": [{"type": "textStyle", "attrs": {"color": "#000000", "fontSize": null}}]}]}, {"type": "paragraph", "attrs": {"textAlign": null}}]}	PUBLISHED	0	2026-04-06 22:07:00	\N	34	2026-04-09 22:07:39.527978	2026-04-10 07:47:10.755375	f	\N	t	
\.


--
-- Data for Name: post; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.post (id, board_id, user_id, title, content_json, extra_data, status, view_count, create_date, modify_date, content, is_deleted, delete_date) FROM stdin;
3	2	1	필드인데  이게 뭐인가??	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "잘못되어가네", "type": "text"}]}]}	{}	published	25	2026-03-15 14:57:52.454476	\N	<p>잘못되어가네</p>	f	\N
4	1	1	힘들어	null	{}	published	26	2026-04-09 20:43:47.711329	2026-04-09 20:55:34.794244	<h1></h1>	f	\N
2	1	1	ㅈㅈ	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "ㅈㅈ", "type": "text"}]}]}	{}	published	60	2026-03-15 10:53:16.87598	\N	<p>ㅈㅈ</p>	f	\N
8	3	1	test	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "testtest", "type": "text"}]}]}	{}	published	2	2026-04-10 18:30:48.380235	\N	<p>testtest</p>	f	\N
7	3	1	nm	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "m", "type": "text"}]}]}	{}	published	6	2026-04-09 21:24:56.711428	\N	<p>m</p>	f	\N
6	1	1	11	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "ㅓㅗㅓㅗ", "type": "text"}]}]}	{}	published	34	2026-04-09 20:56:52.382474	2026-04-09 21:05:26.877981	<p>ㅓㅗㅓㅗ</p>	f	\N
1	1	1	공지 테스트	{"type": "doc", "content": [{"type": "paragraph", "attrs": {"textAlign": null}, "content": [{"text": "이것 뭐..", "type": "text"}]}, {"type": "paragraph", "attrs": {"textAlign": null}}, {"type": "heading", "attrs": {"level": 3, "textAlign": null}, "content": [{"text": "수정까지 되는거야??", "type": "text", "marks": [{"type": "bold"}]}]}, {"type": "paragraph", "attrs": {"textAlign": null}}]}	{}	published	81	2026-03-06 10:33:52.420212	2026-03-06 14:09:57.088126	<p>이것 뭐..</p><p></p><h3><strong>수정까지 되는거야??</strong></h3><p></p>	f	\N
5	1	1		null	{}	published	11	2026-04-09 20:44:30.820764	\N		t	2026-04-09 20:55:12.467293
\.


--
-- Data for Name: post_reaction; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.post_reaction (user_id, post_id, reaction_type) FROM stdin;
\.


--
-- Data for Name: post_read; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.post_read (id, user_id, post_id, first_read_at, last_read_at, read_count, device_category) FROM stdin;
1	1	1	2026-03-06 13:27:15.070072	2026-03-06 13:27:15.070081	1	\N
2	1	3	2026-03-15 14:58:39.585256	2026-03-15 14:58:39.58527	1	\N
3	1	2	2026-03-15 14:59:01.701053	2026-03-15 14:59:01.701088	1	\N
4	3	1	2026-03-18 14:39:41.257151	2026-03-18 14:39:41.257158	1	\N
5	3	2	2026-03-18 14:39:56.616713	2026-03-18 14:39:56.616718	1	\N
6	3	3	2026-03-18 14:40:17.255515	2026-03-18 14:40:17.255522	1	\N
7	1	4	2026-04-09 20:43:49.444829	2026-04-09 20:43:49.444843	1	\N
8	1	5	2026-04-09 20:44:33.111355	2026-04-09 20:44:33.11137	1	\N
9	1	6	2026-04-09 20:56:54.386893	2026-04-09 20:56:54.386906	1	\N
10	1	7	2026-04-09 21:24:57.56505	2026-04-09 21:24:57.565063	1	\N
11	1	8	2026-04-10 18:30:50.245619	2026-04-10 18:30:50.245627	1	\N
\.


--
-- Data for Name: post_tag; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.post_tag (post_id, tag_id) FROM stdin;
\.


--
-- Data for Name: push_subscription; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.push_subscription (id, user_id, endpoint, p256dh, auth) FROM stdin;
11	1	https://fcm.googleapis.com/fcm/send/fr19O-vTBFU:APA91bG1WfqPdJp13V0by8-uNOba07GfZOx3rytes0CvNhJSBTZaXh9Hv7xtulyo-Dy8HTqoRWYJvZCbWoPNlHQoTUq_a9fDfGlq6HUfxKwNrgJ2AeOP6BTbKF0nc3CQOElZFK9e6szt	BD1D17niafoCqqRN5PCGptHTH0gFcX3W1j7A5_JBiUD_ChrW6t2pbCkxxRIeCjEvHX9wemJKr6yzOPieq-tCL2c	cxCYtScE8ciO_kQJf6xIvw
\.


--
-- Data for Name: question; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.question (id, subject, content, create_date, user_id, modify_date, is_deleted, delete_date) FROM stdin;
1	이게 되나?	된다고	2026-03-06 13:33:18.072388	1	\N	f	\N
2	44	44	2026-03-20 10:57:28.469412	1	\N	f	\N
3	아진짜	답답하다	2026-03-20 10:59:45.249167	1	\N	t	2026-03-20 12:36:20.296838
4	1	1	2026-03-20 12:26:59.108408	1	\N	t	2026-03-20 12:44:05.34958
5	도메인으로 가	됨	2026-03-20 13:22:16.996104	1	\N	f	\N
6	vv	v	2026-03-25 10:15:33.91353	1	\N	f	\N
\.


--
-- Data for Name: question_image; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.question_image (id, filename, original_name, question_id, thumbnail_filename) FROM stdin;
\.


--
-- Data for Name: question_reaction; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.question_reaction (user_id, question_id, reaction_type) FROM stdin;
\.


--
-- Data for Name: question_read_user; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.question_read_user (user_id, question_id) FROM stdin;
1	1
\.


--
-- Data for Name: service_app; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.service_app (id, name, engine_id, config, is_active, created_at) FROM stdin;
1	기본 댓글 서비스	basic_comment_v1	{"allow_anonymous": false}	t	2026-04-10 18:27:40.850144
2	기본 업로드 서비스	basic_upload_v1	{"multiple": true}	t	2026-04-10 18:27:40.853197
\.


--
-- Data for Name: service_engine; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.service_engine (id, registry_id, version, frontend_plugin, config_schema, is_active, created_at) FROM stdin;
basic_comment	comment	1.0.0	CommentEngine	{}	t	2026-03-19 16:49:20.794881
basic_comment_v1	comment	1.0.0	CommentEngine	{"allow_anonymous": false}	t	2026-04-10 18:27:40.843579
basic_upload_v1	upload	1.0.0	UploadEngine	{"multiple": true}	t	2026-04-10 18:27:40.84359
\.


--
-- Data for Name: service_instance; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.service_instance (id, name, is_active, created_at, service_app_ids) FROM stdin;
1	표준 게시판 서비스 세트	t	2026-04-10 18:27:40.857956	[2, 1]
\.


--
-- Data for Name: service_registry; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.service_registry (id, name, description) FROM stdin;
comment	댓글표준	기본 댓글 시스템
upload	파일 업로드	이미지 및 문서를 게시물에 첨부할 수 있게 합니다.
\.


--
-- Data for Name: system_config; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_config (key, value, description, updated_date) FROM stdin;
landing_page	{"value": "/v1"}	\N	2026-03-29 10:11:52.315319
site_title	{"value": "My "}	\N	2026-03-29 10:51:29.587495
theme_mode	{"value": "dark"}	\N	2026-03-29 10:51:29.720502
\.


--
-- Data for Name: tag; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tag (id, name, color) FROM stdin;
\.


--
-- Data for Name: user_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_profiles (user_id, rank_level, is_active, employee_no, resident_no, joined_date, bank_name, account_no, admin_memo) FROM stdin;
1	4	t	\N	\N	\N	\N	\N	\N
4	2	t	\N	\N	\N	\N	\N	\N
5	3	t	\N	\N	\N	\N	\N	\N
3	1	t	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: user_session; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_session (id, user_id, session_key, device_category, status, device_name, ip_address, login_at, logout_at, last_activity) FROM stdin;
57	5	a2c02bcc-ca6b-4355-9459-cfbbaa1b9209	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 17:54:56.698295	2026-03-19 13:35:05.272268	2026-03-06 17:54:56.698683
1	1	ddb9f11d-99e9-46ff-8466-143302f91a8b	WORKSPACE	LOGOUT	\N	\N	2026-03-03 15:52:39.221537	2026-03-03 16:08:06.865922	2026-03-03 15:52:39.223115
42	1	4f779405-d27b-40d3-a788-a5cec7a126de	MOBILE	KICKED_OUT	\N	\N	2026-03-06 14:03:35.116921	2026-03-06 19:22:18.121647	2026-03-06 14:03:35.11894
2	1	a394623c-41a8-458a-8fd2-7804415f1fab	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:10:38.490256	2026-03-03 16:10:43.023246	2026-03-03 16:10:38.491976
3	1	e54f95e2-27c3-4da4-9135-40d3ee9aebfc	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:11:55.111708	2026-03-03 16:18:08.223376	2026-03-03 16:11:55.112095
4	1	71ba41a8-c8dc-41ef-82eb-a53480ab5220	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:18:27.540162	2026-03-03 16:25:38.302432	2026-03-03 16:18:27.541526
5	1	6c77bc1b-255c-46e3-9be3-8d9fc31bfe1e	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:25:47.037782	2026-03-03 16:25:55.204997	2026-03-03 16:25:47.040078
6	1	1e0ac3e2-2bff-4c55-891f-51c2aa3fb493	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:26:00.063065	2026-03-03 16:32:13.384254	2026-03-03 16:26:00.063379
7	1	2496eacc-7140-4b4e-ae76-1ac00221a0f3	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 16:32:21.332051	2026-03-03 16:33:23.494143	2026-03-03 16:32:21.33403
8	1	53b72c0c-cfac-4863-b39b-7075dca4986f	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:33:23.499057	2026-03-03 16:33:29.748998	2026-03-03 16:33:23.501005
9	1	ad19b414-83ee-4894-ab6f-71e796a79262	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 16:33:50.086215	2026-03-03 16:47:48.13508	2026-03-03 16:33:50.086612
10	1	90c43eff-4fdf-4b66-9aad-2153dae738ca	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:47:48.139836	2026-03-03 16:57:24.855784	2026-03-03 16:47:48.141807
11	3	3f98f411-c420-446e-8f65-8fb77a7a031a	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:57:43.314835	2026-03-03 16:57:46.230429	2026-03-03 16:57:43.315179
12	4	5b1ccee9-4690-41d0-9aae-70bd5a5b2e3f	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:57:58.779275	2026-03-03 16:58:03.216874	2026-03-03 16:57:58.779648
13	1	8de73c97-d6f0-48c0-9ca3-c90abeb7dfca	WORKSPACE	LOGOUT	\N	\N	2026-03-03 16:58:14.360397	2026-03-03 17:01:22.752145	2026-03-03 16:58:14.360767
14	1	8a887169-1c83-4fb7-aaec-c347afff4c47	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 17:01:29.41264	2026-03-03 17:08:38.817906	2026-03-03 17:01:29.413096
15	1	a62b01cc-f4f3-408f-a84d-6297277a65fa	WORKSPACE	LOGOUT	\N	\N	2026-03-03 17:08:38.822336	2026-03-03 17:29:50.627009	2026-03-03 17:08:38.823966
17	1	356aaff2-793c-4cda-8631-5c028d58be61	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 17:30:33.19445	2026-03-03 18:05:32.401324	2026-03-03 17:30:33.195833
18	1	e1809fc6-08a9-40d4-a293-a5ec20d61358	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:05:32.406568	2026-03-03 18:26:07.275152	2026-03-03 18:05:32.408264
19	1	a7c50c5a-dc0a-4e82-9b84-941d644ba1d7	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:26:15.873285	2026-03-03 18:27:28.715261	2026-03-03 18:26:15.875395
20	1	9dc0f95d-07b7-4242-9e5c-63d43bc59354	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:37:42.399642	2026-03-03 18:40:46.564465	2026-03-03 18:37:42.401346
21	1	8ca50c00-8419-4c37-91ad-7214e045c316	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:45:24.213113	2026-03-03 18:46:30.215841	2026-03-03 18:45:24.213504
22	1	fbf9cfb0-8bba-4820-bd5d-1b19758df7a5	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:48:13.680382	2026-03-03 18:51:16.909019	2026-03-03 18:48:13.681039
23	1	4f3c3f15-3bab-45f6-9645-9d98cd5d4714	WORKSPACE	LOGOUT	\N	\N	2026-03-03 18:51:23.89091	2026-03-03 18:53:05.391126	2026-03-03 18:51:23.893002
24	1	7cfe92cc-a757-469a-afbf-3b89a2bdbf7d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 19:00:01.021649	2026-03-03 19:03:23.114163	2026-03-03 19:00:01.022805
25	1	f39317bc-f02b-4c11-866d-088db93fa3f1	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 19:03:23.118855	2026-03-03 19:29:16.256117	2026-03-03 19:03:23.120503
26	1	176b6080-2ea3-413f-86f1-d6cadd2d0fce	WORKSPACE	KICKED_OUT	\N	\N	2026-03-03 19:29:16.261877	2026-03-03 19:30:57.749189	2026-03-03 19:29:16.263614
27	1	73429293-ce41-4981-8781-4df60011dfa5	WORKSPACE	LOGOUT	\N	\N	2026-03-03 19:30:57.752836	2026-03-03 19:34:02.801919	2026-03-03 19:30:57.754415
28	1	5d9dd58f-f6dd-4023-9565-c6a01cd476bd	WORKSPACE	LOGOUT	\N	\N	2026-03-03 19:34:12.87771	2026-03-06 09:17:41.783878	2026-03-03 19:34:12.878119
29	1	a99a37af-4953-44ea-8115-5457f1803015	WORKSPACE	LOGOUT	\N	\N	2026-03-06 09:37:00.789001	2026-03-06 09:37:57.800759	2026-03-06 09:37:00.790377
30	1	3ea8466d-8f27-43d3-86cb-20e09b55e3a6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 09:38:30.74453	2026-03-06 10:57:25.672168	2026-03-06 09:38:30.744944
31	1	87b96fbf-57f7-419b-8518-7e3d70643b8a	WORKSPACE	LOGOUT	\N	\N	2026-03-06 10:57:25.673868	2026-03-06 11:15:42.808774	2026-03-06 10:57:25.674269
32	1	73a05759-85fe-4141-ba4b-2279084c193d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 11:25:32.812865	2026-03-06 11:37:10.830552	2026-03-06 11:25:32.813229
33	1	096ca681-d0de-487c-9083-41ee6b4b243b	WORKSPACE	LOGOUT	\N	\N	2026-03-06 11:37:10.844996	2026-03-06 13:28:34.766038	2026-03-06 11:37:10.846479
34	1	997a67d2-f64a-4469-bb80-9bd6aaf03875	WORKSPACE	LOGOUT	\N	\N	2026-03-06 13:28:49.947767	2026-03-06 13:30:43.337251	2026-03-06 13:28:49.948134
35	1	99b08820-4c63-4288-b367-203094cfea9b	WORKSPACE	LOGOUT	\N	\N	2026-03-06 13:30:57.700855	2026-03-06 13:36:59.139253	2026-03-06 13:30:57.701441
36	1	4c112a12-bb1c-4a1a-aeaf-5b875eddf76d	WORKSPACE	LOGOUT	\N	\N	2026-03-06 13:37:07.093082	2026-03-06 13:41:27.732904	2026-03-06 13:37:07.093438
37	1	1548b6cd-9acf-4120-a1e0-dec47789f84c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 13:41:35.697033	2026-03-06 13:49:44.281439	2026-03-06 13:41:35.697413
38	1	0482c7be-c8a2-45af-b470-f3f37833d163	WORKSPACE	LOGOUT	\N	\N	2026-03-06 13:49:44.295255	2026-03-06 13:57:29.946413	2026-03-06 13:49:44.297962
39	1	0e9ef5b8-d228-43bc-93b8-e484b020082c	WORKSPACE	LOGOUT	\N	\N	2026-03-06 13:57:38.622735	2026-03-06 13:58:14.054969	2026-03-06 13:57:38.624219
16	1	fad92023-9748-4a28-9b49-98b769920926	MOBILE	KICKED_OUT	\N	\N	2026-03-03 17:11:26.870801	2026-03-06 14:00:03.495892	2026-03-03 17:11:26.871204
41	1	ecccaaac-935f-49e2-9c52-c289a796ac81	MOBILE	KICKED_OUT	\N	\N	2026-03-06 14:00:03.497332	2026-03-06 14:03:35.102412	2026-03-06 14:00:03.497679
40	1	f872481d-9a3f-4966-b3c0-5330c543be4e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 13:58:36.348513	2026-03-06 14:03:55.346486	2026-03-06 13:58:36.348882
43	1	b24c2766-a6c9-4ad8-aecd-7e1c032d0b4e	WORKSPACE	LOGOUT	\N	\N	2026-03-06 14:03:55.349878	2026-03-06 14:08:36.212578	2026-03-06 14:03:55.350578
44	1	173496ef-b91a-464d-9754-71686719abdc	WORKSPACE	LOGOUT	\N	\N	2026-03-06 14:09:14.818479	2026-03-06 14:48:42.449287	2026-03-06 14:09:14.819974
45	1	1950118b-973b-4e67-9b7f-31cfddf7b3ee	WORKSPACE	LOGOUT	\N	\N	2026-03-06 14:48:53.193354	2026-03-06 14:59:28.738171	2026-03-06 14:48:53.195244
46	1	059676de-372e-40cd-b2a4-5854a34ed429	WORKSPACE	LOGOUT	\N	\N	2026-03-06 15:00:06.793515	2026-03-06 15:00:07.798549	2026-03-06 15:00:06.794017
47	1	7132b158-fcfe-48e4-927a-77c58d938e30	WORKSPACE	LOGOUT	\N	\N	2026-03-06 15:00:13.928177	2026-03-06 15:00:41.89852	2026-03-06 15:00:13.928568
48	1	1b029f1a-6d8e-488b-b794-283b90a8df36	WORKSPACE	LOGOUT	\N	\N	2026-03-06 15:01:02.236701	2026-03-06 15:01:29.47295	2026-03-06 15:01:02.237099
49	1	0e10a47e-07c4-4d46-9ba8-5b6f88227c4b	WORKSPACE	LOGOUT	\N	\N	2026-03-06 15:01:42.863324	2026-03-06 17:07:09.644886	2026-03-06 15:01:42.86368
50	1	0dc54c77-2400-4593-b70d-4b359c5f9127	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 17:07:40.818389	2026-03-06 17:39:45.837169	2026-03-06 17:07:40.819955
51	1	8fb8e3e9-dff1-4f7c-8a70-af64d4188885	WORKSPACE	LOGOUT	\N	\N	2026-03-06 17:39:45.841444	2026-03-06 17:42:51.356027	2026-03-06 17:39:45.843145
52	1	73c98cd5-e942-4d36-8a9d-68af86c2c1d3	WORKSPACE	LOGOUT	\N	\N	2026-03-06 17:43:00.688525	2026-03-06 17:43:55.464521	2026-03-06 17:43:00.689921
53	1	65688ab5-a779-483f-aa4f-3fb434b8b6da	WORKSPACE	LOGOUT	\N	\N	2026-03-06 17:44:03.154855	2026-03-06 17:44:42.383611	2026-03-06 17:44:03.156399
54	3	944bcca2-4cac-4937-84a7-b5a433604e90	WORKSPACE	LOGOUT	\N	\N	2026-03-06 17:45:03.351348	2026-03-06 17:52:03.981908	2026-03-06 17:45:03.35163
55	1	9f888a18-5f4c-4fc2-b44f-dc3a0bbb670b	WORKSPACE	LOGOUT	\N	\N	2026-03-06 17:45:48.093245	2026-03-06 17:52:09.589151	2026-03-06 17:45:48.093567
56	1	b041541a-c085-4679-b64c-24914d2b23f4	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 17:52:19.210984	2026-03-06 18:01:19.041878	2026-03-06 17:52:19.212453
58	1	95cfd3a2-99b4-4479-aefc-daa2d562f3fc	WORKSPACE	LOGOUT	\N	\N	2026-03-06 18:01:19.04529	2026-03-06 18:07:39.885579	2026-03-06 18:01:19.046497
59	1	96d33632-97d5-4274-a859-565f31ae5eab	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 18:07:48.656847	2026-03-06 18:12:23.430996	2026-03-06 18:07:48.658433
61	4	3cb428c4-02d9-4255-bb2a-a65648b3e7fa	WORKSPACE	ACTIVE	\N	\N	2026-03-06 18:17:49.395999	\N	2026-03-06 18:17:49.396683
60	1	e01b09eb-a729-4cb2-a445-8500fb9450cc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 18:12:23.435292	2026-03-06 18:22:12.592811	2026-03-06 18:12:23.437
62	1	8ab240d7-ac06-4c19-b0f7-5a9f8fd4ed48	WORKSPACE	LOGOUT	\N	\N	2026-03-06 18:22:12.597433	2026-03-06 18:39:00.693318	2026-03-06 18:22:12.599392
63	1	26058478-da0c-4f3f-805f-a33c78caa029	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 18:39:08.87555	2026-03-06 18:52:10.552307	2026-03-06 18:39:08.878009
65	1	3a9ab44c-eebd-4d96-ae18-9dd931b657d7	WORKSPACE	LOGOUT	\N	\N	2026-03-06 19:01:05.93389	2026-03-06 19:04:13.672953	2026-03-06 19:01:05.936036
64	1	23c242a6-41cd-454c-812d-5e297a6cd882	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 18:52:10.556199	2026-03-06 19:01:05.929451	2026-03-06 18:52:10.558079
140	1	53532a46-0168-4cef-96da-45d452ded85d	WORKSPACE	LOGOUT	\N	\N	2026-03-12 12:53:43.221622	2026-03-12 12:57:23.056272	2026-03-12 12:53:43.2235
66	1	1811bbae-9950-47a6-99c3-249893d36d77	WORKSPACE	KICKED_OUT	\N	\N	2026-03-06 19:04:18.435355	2026-03-06 19:17:42.258421	2026-03-06 19:04:18.436805
67	1	fd51cff8-8a8a-4d3d-b187-080c52f2480f	WORKSPACE	LOGOUT	\N	\N	2026-03-06 19:17:42.263522	2026-03-06 19:20:29.134079	2026-03-06 19:17:42.26542
69	1	ef9f3723-c926-410b-b2b9-beb89d4d8b15	MOBILE	ACTIVE	\N	\N	2026-03-06 19:22:18.123413	\N	2026-03-06 19:22:18.123813
68	1	163ad668-3efd-498c-9e48-12d2be0b5396	WORKSPACE	LOGOUT	\N	\N	2026-03-06 19:20:36.385078	2026-03-08 22:51:37.695841	2026-03-06 19:20:36.387007
70	1	f5bf7b4b-fc6f-485b-b536-015a6df0d056	WORKSPACE	LOGOUT	\N	\N	2026-03-08 22:51:49.713596	2026-03-08 22:52:41.756199	2026-03-08 22:51:49.716264
71	1	2f1739af-2a36-4573-b4d1-b931087d5d60	WORKSPACE	KICKED_OUT	\N	\N	2026-03-08 22:52:52.485278	2026-03-09 17:39:39.546409	2026-03-08 22:52:52.48592
72	1	d313adce-2713-44e6-ba1b-e086e46fc750	WORKSPACE	KICKED_OUT	\N	\N	2026-03-09 17:39:39.558044	2026-03-09 19:06:20.027799	2026-03-09 17:39:39.561041
73	1	216447b0-f456-49c6-9f2e-58afe365b05c	WORKSPACE	LOGOUT	\N	\N	2026-03-09 19:06:20.036995	2026-03-11 12:11:43.165154	2026-03-09 19:06:20.040187
74	1	3a8f95e2-cfc5-47d6-8255-b8bab180c777	WORKSPACE	LOGOUT	\N	\N	2026-03-11 12:12:03.078437	2026-03-11 16:02:16.340516	2026-03-11 12:12:03.080955
75	1	0139a319-f639-4264-935d-a289ac069fdc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 16:02:23.532579	2026-03-11 16:20:02.816319	2026-03-11 16:02:23.534274
76	1	32d70de9-be02-40ef-9391-7118005c2dc3	WORKSPACE	LOGOUT	\N	\N	2026-03-11 16:20:02.821083	2026-03-11 16:22:17.431867	2026-03-11 16:20:02.822764
77	1	101ecc3d-7cd3-4afc-8273-7b05891849f3	WORKSPACE	LOGOUT	\N	\N	2026-03-11 16:22:30.658653	2026-03-11 16:27:04.856835	2026-03-11 16:22:30.659072
78	1	1934b7f6-1c23-45ce-81c5-eda2a0e28bf8	WORKSPACE	LOGOUT	\N	\N	2026-03-11 16:27:11.589204	2026-03-11 16:36:04.862632	2026-03-11 16:27:11.591383
79	1	6ad2884a-ca47-49f4-92e8-320bd7ea3217	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 16:36:15.061201	2026-03-11 16:36:15.984138	2026-03-11 16:36:15.061667
80	1	05a0ebb5-7a33-4d59-9f14-78a046e6334d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 16:36:15.985944	2026-03-11 17:41:24.813903	2026-03-11 16:36:15.986606
81	1	6b088c7f-ae6e-480a-b151-37f129f8a7e2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 17:41:24.81929	2026-03-11 17:50:51.325357	2026-03-11 17:41:24.821238
82	1	9001d05a-a60d-4bb2-91d3-0b48812da473	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 17:50:51.330739	2026-03-11 18:26:56.237681	2026-03-11 17:50:51.33267
83	1	d65b9233-ddd1-4079-bc73-efcca866651e	WORKSPACE	LOGOUT	\N	\N	2026-03-11 18:26:56.25112	2026-03-11 19:00:56.984024	2026-03-11 18:26:56.253151
84	1	2d83cf40-a928-40f9-aed6-de93a88cc981	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 19:01:05.54687	2026-03-11 19:52:36.411414	2026-03-11 19:01:05.54893
85	1	8824c96f-7875-42ed-8f5e-95e2a49d9c86	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 19:52:36.417074	2026-03-11 19:56:57.814347	2026-03-11 19:52:36.419227
86	1	75762241-73cd-4329-a249-14f519d9b9ee	WORKSPACE	LOGOUT	\N	\N	2026-03-11 19:56:57.81952	2026-03-11 20:27:40.509561	2026-03-11 19:56:57.821554
87	3	e7bdbdc3-7bba-4256-81a6-b0dd31572fb0	MOBILE	KICKED_OUT	\N	\N	2026-03-11 20:24:41.549103	2026-03-11 20:31:44.805684	2026-03-11 20:24:41.549713
89	3	0927fc21-75a3-4523-8e9c-2d2335d218e7	MOBILE	KICKED_OUT	\N	\N	2026-03-11 20:31:44.811097	2026-03-11 20:31:45.92355	2026-03-11 20:31:44.812934
90	3	4d0ddb46-4775-4e21-824e-8d1d6d1511ff	MOBILE	KICKED_OUT	\N	\N	2026-03-11 20:31:45.925253	2026-03-11 20:31:55.629873	2026-03-11 20:31:45.925705
88	1	65b19317-09a8-4049-ada9-4d41b9efe6f6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 20:27:48.344104	2026-03-11 20:33:43.313268	2026-03-11 20:27:48.344484
92	1	b86c8f53-0a3d-44ba-b874-956798d615b0	WORKSPACE	LOGOUT	\N	\N	2026-03-11 20:33:43.316268	2026-03-11 20:49:36.789266	2026-03-11 20:33:43.316934
93	1	72fe5002-30ee-47e0-ba06-03e7f46c5314	WORKSPACE	LOGOUT	\N	\N	2026-03-11 20:49:43.142392	2026-03-11 20:52:04.478849	2026-03-11 20:49:43.144999
91	3	34ca953d-ccfb-4637-80a1-7288db9b9735	MOBILE	KICKED_OUT	\N	\N	2026-03-11 20:31:55.631528	2026-03-11 20:57:14.925577	2026-03-11 20:31:55.631917
94	1	caee6d2e-95a2-40ac-99d2-1dab07e71288	WORKSPACE	LOGOUT	\N	\N	2026-03-11 20:52:13.425033	2026-03-11 21:14:42.847124	2026-03-11 20:52:13.425742
96	1	5e5a9118-756b-4955-9858-9814443d5f86	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:14:48.988008	2026-03-11 21:15:15.899043	2026-03-11 21:14:48.990182
97	1	355128ce-6171-422e-aa7d-4d9fefa9b474	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:15:21.979128	2026-03-11 21:19:13.885359	2026-03-11 21:15:21.979636
98	1	54f02d97-6022-4f70-9bce-c7faa0ff127f	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:19:23.532718	2026-03-11 21:30:57.562017	2026-03-11 21:19:23.533117
99	1	6cc2d781-cdfc-458c-800c-cb45215a75a6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 21:31:06.411135	2026-03-11 21:41:01.12861	2026-03-11 21:31:06.412897
100	1	385d124c-0bed-40c5-80cf-5fa833725923	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:41:01.144601	2026-03-11 21:47:11.346891	2026-03-11 21:41:01.146594
101	1	7fcb5302-5165-484b-8ac3-e5ce3057b14c	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:47:19.171662	2026-03-11 21:47:45.949972	2026-03-11 21:47:19.173906
102	1	a18b9d93-0413-44cf-b465-1cb389a072a2	WORKSPACE	LOGOUT	\N	\N	2026-03-11 21:47:52.637252	2026-03-11 22:01:23.708685	2026-03-11 21:47:52.637718
103	1	b124924d-7b33-4932-bf33-938ed33c461a	WORKSPACE	LOGOUT	\N	\N	2026-03-11 22:02:27.646531	2026-03-11 22:03:05.082466	2026-03-11 22:02:27.64838
104	1	47044612-8f72-4858-bb9f-5704ca39a43a	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 22:03:11.797472	2026-03-11 22:15:51.671313	2026-03-11 22:03:11.79795
105	1	567a5e93-9750-49b8-afe3-a42fc2a01e8e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-11 22:15:51.685807	2026-03-12 07:19:14.008105	2026-03-11 22:15:51.687646
106	1	08237b2a-b027-4aea-b642-c428984002c4	WORKSPACE	LOGOUT	\N	\N	2026-03-12 07:19:14.024009	2026-03-12 07:31:18.032587	2026-03-12 07:19:14.026407
107	1	06b0c9a4-6fd4-44c7-be91-601d59ce83e6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 07:31:26.173178	2026-03-12 07:33:54.137587	2026-03-12 07:31:26.175196
108	1	71007b6b-b13b-4f93-b5f0-7fd7127c0958	WORKSPACE	LOGOUT	\N	\N	2026-03-12 07:33:54.142132	2026-03-12 07:34:17.133394	2026-03-12 07:33:54.144002
109	1	0d103e0d-0093-4e62-b240-f996f86d5346	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 07:34:25.541813	2026-03-12 07:38:57.567498	2026-03-12 07:34:25.54228
110	1	982af712-50f8-4513-962e-60aadb68c1a6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 07:38:57.582725	2026-03-12 07:47:25.764929	2026-03-12 07:38:57.584633
111	1	1eb7e93e-9504-42b6-8d58-32ed416fa3ee	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 07:47:25.770366	2026-03-12 08:22:21.161425	2026-03-12 07:47:25.772223
112	1	d1298e35-b874-4915-942f-798742875b03	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 08:22:21.176502	2026-03-12 08:26:11.189026	2026-03-12 08:22:21.178803
113	1	c34223ec-ecf2-4fe3-acad-bf8fcf8d08a0	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 08:26:11.19397	2026-03-12 08:35:38.331385	2026-03-12 08:26:11.195752
114	1	cda628e4-770e-4dde-8e8c-38f38fbf5886	WORKSPACE	LOGOUT	\N	\N	2026-03-12 08:35:38.337872	2026-03-12 08:38:19.512924	2026-03-12 08:35:38.339773
95	3	e91b370f-d4a2-4a7b-8829-7a420cda19be	MOBILE	KICKED_OUT	\N	\N	2026-03-11 20:57:14.927419	2026-03-12 09:09:05.6537	2026-03-11 20:57:14.927836
115	1	dc59969c-e26c-43d5-baa9-ea94c08dad4c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 08:38:24.825995	2026-03-12 09:09:38.016506	2026-03-12 08:38:24.828105
117	1	b4326efb-0a9d-4551-bc4a-6de56b7fb4df	WORKSPACE	LOGOUT	\N	\N	2026-03-12 09:09:38.018536	2026-03-12 09:10:25.53468	2026-03-12 09:09:38.019137
116	3	28d554d8-8a08-4c1b-972b-2beea4b63ae7	MOBILE	KICKED_OUT	\N	\N	2026-03-12 09:09:05.66907	2026-03-12 09:19:25.439109	2026-03-12 09:09:05.671283
118	1	f6ed4370-1757-449d-9406-11afb3e5e38f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 09:10:33.311335	2026-03-12 09:20:35.340367	2026-03-12 09:10:33.311764
120	1	5c183f66-91e3-41a7-be1e-f7a6d15438f4	WORKSPACE	LOGOUT	\N	\N	2026-03-12 09:20:35.344345	2026-03-12 09:24:47.457856	2026-03-12 09:20:35.345065
119	3	a4b5511d-6210-4f51-a043-bd376b0a3457	MOBILE	KICKED_OUT	\N	\N	2026-03-12 09:19:25.455827	2026-03-12 09:25:53.695825	2026-03-12 09:19:25.457873
121	1	a7a1767f-79eb-44b3-9cdf-bca339d67d92	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 09:24:54.741362	2026-03-12 09:37:04.78257	2026-03-12 09:24:54.742957
122	3	2ea43ed9-5d6d-4099-8c9f-5d942f7ecc33	MOBILE	KICKED_OUT	\N	\N	2026-03-12 09:25:53.697463	2026-03-12 09:38:13.410935	2026-03-12 09:25:53.697987
123	1	b717a15d-f380-469c-9b34-d87d62ae6e6e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 09:37:04.798582	2026-03-12 09:47:23.823944	2026-03-12 09:37:04.800903
139	1	aad4c8c7-a7f9-4f9e-a7df-3c662025395b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:48:24.855825	2026-03-12 12:53:43.216506	2026-03-12 12:48:24.857824
486	3	afafe0b8-dfd6-4f0c-914b-9a434364aa4a	MOBILE	EXPIRED	Mozilla/5.0 (Android 13; Mobile; rv:149.0) Gecko/149.0 Firefox/149.0	172.18.0.3	2026-04-06 19:04:58.17537	2026-04-09 09:29:21.36497	2026-04-06 19:05:02.281708
125	1	97c7b9d2-97f9-40d4-82e3-ad75e2ee5475	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 09:47:23.838517	2026-03-12 10:49:40.766661	2026-03-12 09:47:23.840067
141	1	c10c6222-a700-4606-b301-54de382bd1fc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:57:31.967447	2026-03-12 13:13:49.236527	2026-03-12 12:57:31.969548
126	1	bb8569f4-22fb-43db-bd22-597fd45c6d6e	WORKSPACE	LOGOUT	\N	\N	2026-03-12 10:49:40.771311	2026-03-12 10:57:17.01277	2026-03-12 10:49:40.773038
124	3	26be0390-e4dd-44f2-b60b-4392844cb85f	MOBILE	KICKED_OUT	\N	\N	2026-03-12 09:38:13.412621	2026-03-12 11:23:37.512865	2026-03-12 09:38:13.413068
142	1	36dc806b-48bc-4468-9a97-ad89ea108634	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 13:13:49.240991	2026-03-12 13:15:30.764098	2026-03-12 13:13:49.24277
127	1	24df511f-76bd-4ff9-9b4c-19d66aa70865	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 11:00:46.234443	2026-03-12 11:25:08.940602	2026-03-12 11:00:46.23512
128	3	fa6dafd2-b482-4768-b65e-5df698a26eb7	MOBILE	KICKED_OUT	\N	\N	2026-03-12 11:23:37.526868	2026-03-12 11:26:56.478164	2026-03-12 11:23:37.529086
129	1	6d7cde70-f30b-4d01-939b-2c97cef0c1fb	WORKSPACE	LOGOUT	\N	\N	2026-03-12 11:25:08.955428	2026-03-12 11:27:57.228052	2026-03-12 11:25:08.957542
143	1	8d3eb850-fc28-4ddb-807f-e9e5e5441315	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 13:15:30.769248	2026-03-12 13:28:38.485781	2026-03-12 13:15:30.771079
131	1	d66c79aa-d01e-43ae-92e5-d398e4038a07	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 11:28:36.085996	2026-03-12 11:54:00.8471	2026-03-12 11:28:36.08635
132	1	6389e69e-2f2e-4929-829a-bfb9185106da	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 11:54:00.860647	2026-03-12 12:04:12.735651	2026-03-12 11:54:00.862378
144	1	eb26e955-2467-4147-b361-98a1e57fd517	WORKSPACE	LOGOUT	\N	\N	2026-03-12 13:28:38.490722	2026-03-12 13:45:23.802435	2026-03-12 13:28:38.492437
133	1	784c3ba4-2113-4994-a520-506409dd4116	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:04:12.749971	2026-03-12 12:20:53.374065	2026-03-12 12:04:12.751492
134	1	7ba90dd1-4f7c-472f-8bce-37707a16b05b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:20:53.37911	2026-03-12 12:32:54.646005	2026-03-12 12:20:53.380823
145	1	ab7de986-f2ac-4377-a288-6cca7bbc01ee	WORKSPACE	LOGOUT	\N	\N	2026-03-12 13:45:36.950133	2026-03-12 13:46:56.619652	2026-03-12 13:45:36.950564
135	1	5a428a8b-1ecb-4a2d-ab34-636a718e4bbb	WORKSPACE	LOGOUT	\N	\N	2026-03-12 12:32:54.660536	2026-03-12 12:37:50.848787	2026-03-12 12:32:54.662773
136	1	b93d6236-c462-479b-8b10-85cdc88291dd	WORKSPACE	LOGOUT	\N	\N	2026-03-12 12:38:00.66281	2026-03-12 12:38:49.508549	2026-03-12 12:38:00.664773
146	1	b07e744a-a3c4-497e-975b-15900c97118c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 13:47:15.557283	2026-03-12 13:53:52.454017	2026-03-12 13:47:15.557737
137	1	5b18d21e-0925-4587-9a39-8050f7864017	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:38:57.190049	2026-03-12 12:42:14.887225	2026-03-12 12:38:57.190698
138	1	22bad072-a4e9-4358-9e56-a7a2d35ddc56	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 12:42:14.902322	2026-03-12 12:48:24.850842	2026-03-12 12:42:14.904392
147	1	054fbb52-32b5-445c-9f15-e4ac1f88685b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 13:53:52.459482	2026-03-12 13:56:35.866315	2026-03-12 13:53:52.461066
148	1	6e3eb591-c848-41cb-8929-94c98b35342e	WORKSPACE	LOGOUT	\N	\N	2026-03-12 13:56:35.871115	2026-03-12 13:57:47.217375	2026-03-12 13:56:35.873023
149	1	1e732960-5c61-4901-b270-7ca0600eb229	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 14:46:16.245178	2026-03-12 14:55:31.687242	2026-03-12 14:46:16.247113
150	1	15b16573-6534-4660-a52b-b1245490b9c0	WORKSPACE	LOGOUT	\N	\N	2026-03-12 14:55:31.692386	2026-03-12 14:58:57.04714	2026-03-12 14:55:31.694175
151	1	ebfda970-3c06-4e98-9993-cd8bb6f64135	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 14:59:02.983428	2026-03-12 15:10:08.40352	2026-03-12 14:59:02.98586
152	1	763b5c40-bafc-4297-acb5-0121dfcf5233	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:10:08.407825	2026-03-12 15:15:03.255489	2026-03-12 15:10:08.410077
153	1	4234cb07-a67d-4a25-b41a-a67b4ee33723	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:15:03.259974	2026-03-12 15:20:37.191968	2026-03-12 15:15:03.261514
154	1	140719c3-a3ac-4324-b589-b4fb477e4f6a	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:20:37.205801	2026-03-12 15:27:24.913373	2026-03-12 15:20:37.207327
155	1	4be99104-ddaf-43bc-abf8-ee53b24d77e9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:27:24.91835	2026-03-12 15:37:38.245405	2026-03-12 15:27:24.920514
161	1	3ca5ea02-979f-49b8-871a-14347e8d0e49	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 16:50:52.713456	2026-03-12 16:55:56.267701	2026-03-12 16:50:52.715667
156	1	6767e023-8f83-469d-b9fa-202e4f1ebbf8	WORKSPACE	LOGOUT	\N	\N	2026-03-12 15:37:38.259956	2026-03-12 15:41:25.154932	2026-03-12 15:37:38.262074
157	1	4361a025-8a16-4ea7-8f8e-25e965fef686	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:41:33.635478	2026-03-12 15:59:26.901833	2026-03-12 15:41:33.637412
158	1	470856eb-3efc-4eb2-92eb-669d48cad62e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 15:59:26.908533	2026-03-12 16:26:00.192291	2026-03-12 15:59:26.910327
159	1	1684d2a0-bc48-4b00-98a0-f053cfb148ad	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 16:26:00.197427	2026-03-12 16:34:47.425714	2026-03-12 16:26:00.199187
160	1	25cbbb54-9102-465b-8e10-3fa09f4d3ff3	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 16:34:47.432112	2026-03-12 16:50:52.708466	2026-03-12 16:34:47.434323
162	1	9d4f0af5-6238-4693-8046-0ca7bc8f0e96	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 16:55:56.273143	2026-03-12 17:07:39.500424	2026-03-12 16:55:56.275014
163	1	9801f90b-d1c4-4808-8679-3bc26a20a48f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 17:07:39.505925	2026-03-12 18:08:27.009998	2026-03-12 17:07:39.507655
164	1	680b3bec-13c6-43a0-8b72-51fbf5a22e76	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 18:08:27.0242	2026-03-12 18:18:39.478397	2026-03-12 18:08:27.026086
165	1	ac72b554-80bc-4cee-bab8-993eaf32bd38	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 18:18:39.483659	2026-03-12 18:29:55.484975	2026-03-12 18:18:39.485595
166	1	ec1f6ebf-5545-4117-bade-6eebcadd2791	WORKSPACE	LOGOUT	\N	\N	2026-03-12 18:29:55.490506	2026-03-12 18:33:02.78738	2026-03-12 18:29:55.492832
167	1	afe5f69b-0ed3-4d5f-8c9a-c74c087fd2db	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 18:47:16.652624	2026-03-12 18:57:45.082741	2026-03-12 18:47:16.654493
168	1	009e8a5a-3d62-4b13-bd21-0fc54013d1ce	WORKSPACE	KICKED_OUT	\N	\N	2026-03-12 18:57:45.087793	2026-03-12 19:01:25.660908	2026-03-12 18:57:45.089774
169	1	3a6f5594-ff13-4162-a0d2-cb15ffdf0187	WORKSPACE	LOGOUT	\N	\N	2026-03-12 19:01:25.665592	2026-03-14 22:03:25.510529	2026-03-12 19:01:25.667167
170	1	e7495b86-4a24-45f7-9233-296b81ed534e	WORKSPACE	LOGOUT	\N	\N	2026-03-14 22:14:59.84113	2026-03-14 22:29:08.858008	2026-03-14 22:14:59.843372
171	1	7106cb91-509b-46ff-b264-303bb8dcec83	WORKSPACE	KICKED_OUT	\N	\N	2026-03-14 22:31:28.227499	2026-03-14 22:31:30.181398	2026-03-14 22:31:28.228168
172	1	c0a258fa-ab7a-4991-9534-414769217f6a	WORKSPACE	KICKED_OUT	\N	\N	2026-03-14 22:31:30.184324	2026-03-14 22:31:45.016856	2026-03-14 22:31:30.185141
173	1	1956d43f-979e-4d8d-9b50-687f6a7d5d2c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-14 22:31:45.030174	2026-03-15 10:20:04.411605	2026-03-14 22:31:45.030885
174	1	748d5b40-1629-4462-90d5-4256420db38b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:20:04.431784	2026-03-15 10:24:52.314766	2026-03-15 10:20:04.435238
175	1	e9697679-76da-4a7a-9062-96f5aebe2e43	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:24:52.323175	2026-03-15 10:26:52.702556	2026-03-15 10:24:52.32594
176	1	71573d99-657b-4321-86ef-3c0b0eb69133	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:26:52.711865	2026-03-15 10:36:13.795965	2026-03-15 10:26:52.714931
177	1	f1d12f87-8b00-49ae-9753-e5f221f6b62e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:36:13.80402	2026-03-15 10:39:14.526121	2026-03-15 10:36:13.806815
178	1	c1f18fd2-d825-4fb7-a4d3-4a716686732b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:39:14.534213	2026-03-15 10:44:53.695784	2026-03-15 10:39:14.537015
179	1	98b4cb56-089e-4c72-9a70-af6a5abba3d0	WORKSPACE	LOGOUT	\N	\N	2026-03-15 10:44:53.70308	2026-03-15 10:57:09.968203	2026-03-15 10:44:53.705836
180	1	42422262-62be-415c-b043-0a3682b4f316	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 10:57:17.978893	2026-03-15 11:03:32.420464	2026-03-15 10:57:17.982596
181	1	c0880b9c-3f50-47ae-b04e-09a0845f5315	WORKSPACE	LOGOUT	\N	\N	2026-03-15 11:03:32.428681	2026-03-15 14:53:43.308351	2026-03-15 11:03:32.432336
182	1	7225d2d2-2094-406c-9b13-0cb96ec0de53	WORKSPACE	LOGOUT	\N	\N	2026-03-15 14:54:23.740349	2026-03-15 14:56:59.309605	2026-03-15 14:54:23.741202
183	1	d51a9621-7f00-4919-8206-cccd993bc230	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 14:57:13.02057	2026-03-15 15:02:43.082564	2026-03-15 14:57:13.021386
184	1	5c58f804-32e3-451d-bbd1-493aeac63e3a	WORKSPACE	LOGOUT	\N	\N	2026-03-15 15:02:43.092032	2026-03-15 15:11:20.61962	2026-03-15 15:02:43.09506
130	3	ae523fee-06ec-4866-b90d-3a0e1cefd45f	MOBILE	KICKED_OUT	\N	\N	2026-03-12 11:26:56.480316	2026-03-15 18:48:06.905888	2026-03-12 11:26:56.480954
185	1	fbfdc94e-ab57-46a3-91c4-aa1bc6aaec07	WORKSPACE	LOGOUT	\N	\N	2026-03-15 15:11:26.726093	2026-03-15 15:14:21.319325	2026-03-15 15:11:26.729423
232	1	ed35754d-3dc0-48a8-89c9-da33e71d5d9f	WORKSPACE	LOGOUT	\N	\N	2026-03-19 13:33:40.082196	2026-03-19 13:34:51.970326	2026-03-19 13:33:40.084153
186	1	f8501335-5d4a-4f54-a960-14adcaaf69ea	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 15:14:33.512967	2026-03-15 15:23:03.136326	2026-03-15 15:14:33.516246
233	5	f5bb249c-a6f6-447f-8b70-826f8db0ce38	WORKSPACE	LOGOUT	\N	\N	2026-03-19 13:35:05.275102	2026-03-19 13:36:01.704617	2026-03-19 13:35:05.275772
187	1	e4c5c439-8551-4a7f-8fc6-3c77b4702b74	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 15:23:03.147332	2026-03-15 15:34:26.05461	2026-03-15 15:23:03.151607
234	1	1485fdf2-150e-41ed-b17d-f02250987213	WORKSPACE	LOGOUT	\N	\N	2026-03-19 13:36:08.33039	2026-03-19 13:36:43.076263	2026-03-19 13:36:08.330745
188	1	f78a549b-af36-4027-ad34-be2fc40c5298	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 15:34:26.0701	2026-03-15 15:43:03.719611	2026-03-15 15:34:26.072221
235	5	bf78ca00-2237-4bd4-ad11-8e279ed86191	WORKSPACE	LOGOUT	\N	\N	2026-03-19 13:36:51.645476	2026-03-19 13:37:05.908139	2026-03-19 13:36:51.645852
189	1	521311d1-33e7-4746-874c-9a9f8687e5c1	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 15:43:03.724244	2026-03-15 16:36:16.511358	2026-03-15 15:43:03.726339
236	1	506532a4-918c-4cb5-880e-7874ebc52e4a	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 13:37:15.095128	2026-03-19 16:33:13.805123	2026-03-19 13:37:15.095475
190	1	ccb0fd78-ed0a-45c6-b91e-63b7a253215e	WORKSPACE	LOGOUT	\N	\N	2026-03-15 16:36:16.516958	2026-03-15 16:45:48.285199	2026-03-15 16:36:16.519179
191	1	658cca60-7754-47cc-998c-ac2ada9a1c96	WORKSPACE	LOGOUT	\N	\N	2026-03-15 16:45:53.885446	2026-03-15 17:11:23.453019	2026-03-15 16:45:53.885808
237	1	6e1bc0cf-13ce-4a11-86a2-b13eba647fcc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 16:33:13.820338	2026-03-19 16:42:08.338391	2026-03-19 16:33:13.822171
192	1	63ca50b2-b058-4048-ba25-64d6c49116c8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 17:11:30.607975	2026-03-15 17:31:33.700009	2026-03-15 17:11:30.609462
193	1	40dac35d-f98f-4e49-9959-c3433b0ed9d5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 17:31:33.704924	2026-03-15 17:47:59.301922	2026-03-15 17:31:33.70637
238	1	670a1508-4547-42fe-82e2-9c79e299cc42	WORKSPACE	LOGOUT	\N	\N	2026-03-19 16:42:08.342889	2026-03-19 16:47:06.900345	2026-03-19 16:42:08.344961
194	1	ebcd957f-c9c7-41c9-8ab7-4e3f37e6c8d5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 17:47:59.308214	2026-03-15 17:51:20.821533	2026-03-15 17:47:59.310373
195	1	0ec57645-88d0-4deb-afac-88e0594408da	WORKSPACE	LOGOUT	\N	\N	2026-03-15 17:51:20.826139	2026-03-15 17:51:36.686979	2026-03-15 17:51:20.828201
239	1	a14b966d-924e-4023-be7b-2be08e175bc4	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 16:47:14.090065	2026-03-19 16:54:14.759783	2026-03-19 16:47:14.091463
196	1	c871a94c-7174-40c4-a402-7ed3597c0a51	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 17:51:43.959462	2026-03-15 17:57:34.916624	2026-03-15 17:51:43.959966
197	1	1f0a3f27-c834-4f51-8c9a-f82486e8adb3	WORKSPACE	LOGOUT	\N	\N	2026-03-15 17:57:34.921173	2026-03-15 17:58:24.322367	2026-03-15 17:57:34.923106
240	1	fcdc6506-db40-4ea1-bf11-74cd2798c6ce	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 16:54:14.76441	2026-03-19 16:58:32.663727	2026-03-19 16:54:14.766827
198	1	ca1de08e-cf71-4b61-8b6d-4d143482a3de	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 17:58:32.98795	2026-03-15 18:03:19.708833	2026-03-15 17:58:32.989757
199	1	aab5aae0-4f55-4664-a2a1-c8d959d553f6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 18:03:19.713784	2026-03-15 18:09:40.006881	2026-03-15 18:03:19.717114
241	1	6dec3279-6615-47c0-ad67-21bdf946ec55	WORKSPACE	LOGOUT	\N	\N	2026-03-19 16:58:32.668888	2026-03-19 17:03:24.838541	2026-03-19 16:58:32.670636
200	1	941bdf1d-b5f0-4d1e-90fd-89a43794b565	WORKSPACE	LOGOUT	\N	\N	2026-03-15 18:09:40.011241	2026-03-15 18:13:22.93749	2026-03-15 18:09:40.012846
201	1	a9bde185-1d78-4715-8cd1-5eac840c78c5	WORKSPACE	LOGOUT	\N	\N	2026-03-15 18:13:34.665877	2026-03-15 18:42:10.688261	2026-03-15 18:13:34.6678
242	1	f960cec3-9c43-4406-ae79-daebe2d5e59b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:03:33.886552	2026-03-19 17:09:06.052777	2026-03-19 17:03:33.887977
202	1	625c11c2-f33b-4674-84f0-462322c3a847	WORKSPACE	LOGOUT	\N	\N	2026-03-15 18:42:38.006367	2026-03-15 18:49:55.487204	2026-03-15 18:42:38.006731
243	1	ddf29b19-4df7-4a6c-aa61-c7a01b046a25	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:09:06.058002	2026-03-19 17:15:06.697898	2026-03-19 17:09:06.05981
204	3	8205c4b4-1797-45cb-ac38-a3ae510390b5	WORKSPACE	LOGOUT	\N	\N	2026-03-15 18:50:03.851824	2026-03-15 18:50:52.289317	2026-03-15 18:50:03.852185
205	1	f489e15a-2401-4770-95d6-42f07c2bc8b6	WORKSPACE	LOGOUT	\N	\N	2026-03-15 18:51:02.839987	2026-03-15 18:58:25.84693	2026-03-15 18:51:02.840363
244	1	ae9ddad5-76e3-41bb-80dd-d1c7979b0f1d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:15:06.701826	2026-03-19 17:20:43.294629	2026-03-19 17:15:06.703221
206	1	f1c8f702-761d-49ba-ac10-82b4eed1507a	WORKSPACE	LOGOUT	\N	\N	2026-03-15 19:09:04.682251	2026-03-15 21:05:52.425276	2026-03-15 19:09:04.682585
207	1	a2b8059c-6a07-42b4-b98d-663af2f9d999	WORKSPACE	KICKED_OUT	\N	\N	2026-03-15 21:05:59.106614	2026-03-18 15:26:41.021487	2026-03-15 21:05:59.106968
245	1	62984f98-a84d-4048-9bfd-8143758f4175	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:20:43.299566	2026-03-19 17:23:50.555849	2026-03-19 17:20:43.301283
208	1	7d1e7cc9-2c90-4075-806d-4ff2cc08b076	WORKSPACE	LOGOUT	\N	\N	2026-03-18 15:26:41.037239	2026-03-18 15:29:54.769177	2026-03-18 15:26:41.039078
209	1	76ad81ed-4977-49e3-917a-b2a4293525a4	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 15:30:04.040995	2026-03-18 15:42:57.35265	2026-03-18 15:30:04.042979
210	1	618edc60-eeaa-4cac-a7e7-84498009e005	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 15:42:57.366626	2026-03-18 15:48:19.42757	2026-03-18 15:42:57.368387
211	1	f5891924-b5d4-41ac-9f18-548c4a108dad	WORKSPACE	LOGOUT	\N	\N	2026-03-18 15:48:19.431952	2026-03-18 16:17:50.482451	2026-03-18 15:48:19.433865
212	1	c281077c-034d-4ab7-91bd-e64a4c60eb92	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 16:17:56.784859	2026-03-18 17:07:15.590882	2026-03-18 16:17:56.786703
213	1	f3ceaceb-f461-4a9e-80cc-d84d013e9b73	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 17:07:15.60644	2026-03-18 17:17:31.21634	2026-03-18 17:07:15.608404
214	1	1fed45cb-b8a5-485b-ad05-4dbda627937d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 17:17:31.220682	2026-03-18 17:28:48.313616	2026-03-18 17:17:31.222431
215	1	865a2792-016a-490b-8d6d-d9529abbd914	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 17:28:48.318612	2026-03-18 17:43:24.824937	2026-03-18 17:28:48.321523
216	1	b66c1dbd-ae64-424c-9791-a959495cc5d0	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 17:43:24.828764	2026-03-18 17:49:23.509618	2026-03-18 17:43:24.830393
217	1	742a3555-8657-4622-97b2-2a0d75596aa9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 17:49:23.524925	2026-03-18 18:02:38.197313	2026-03-18 17:49:23.52706
203	3	0758c16c-a8c5-441f-a227-25dad1f39147	MOBILE	KICKED_OUT	\N	\N	2026-03-15 18:48:06.908026	2026-03-18 20:37:33.528286	2026-03-15 18:48:06.908378
219	3	5efb825f-d970-4ad2-9e59-590dd6ffc3f7	MOBILE	ACTIVE	\N	\N	2026-03-18 20:37:33.540426	\N	2026-03-18 20:37:33.545109
218	1	32eba2df-ff2c-4932-a106-62292c8977dd	WORKSPACE	KICKED_OUT	\N	\N	2026-03-18 18:02:38.202332	2026-03-19 09:00:29.609818	2026-03-18 18:02:38.204306
220	1	175e6f86-6e7d-4a71-a647-f1ef5a1bc685	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:00:29.625061	2026-03-19 09:04:09.776398	2026-03-19 09:00:29.627095
221	1	36da7d28-613b-4539-81c7-f643599a17f9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:04:09.779903	2026-03-19 09:10:15.85187	2026-03-19 09:04:09.781812
222	1	02acaae2-fbc5-424f-93cc-d4a5a49f02fa	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:10:15.855683	2026-03-19 09:10:16.37502	2026-03-19 09:10:15.857723
223	1	fc5e9201-c5a4-421e-a6eb-fa21a00cc4a1	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:10:16.376332	2026-03-19 09:12:32.500692	2026-03-19 09:10:16.376765
224	1	23d82967-9799-4e7e-9051-c85637cc73cf	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:12:32.504927	2026-03-19 09:13:41.777029	2026-03-19 09:12:32.506731
225	1	abafac91-fc6d-4134-ad0d-c280123c8c74	WORKSPACE	LOGOUT	\N	\N	2026-03-19 09:13:41.791129	2026-03-19 09:15:04.108524	2026-03-19 09:13:41.792526
226	1	f44a11f5-dc33-4b1c-96a0-d1b7bc25c9c8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:15:08.500766	2026-03-19 09:19:04.304546	2026-03-19 09:15:08.503047
227	1	feaddadd-5585-4b2d-982c-2c1437f29eaf	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 09:19:04.308124	2026-03-19 10:04:33.345554	2026-03-19 09:19:04.30969
228	1	f1d87110-dba4-4a98-90d2-b11fc1b69945	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 10:04:33.361165	2026-03-19 10:07:11.467918	2026-03-19 10:04:33.362972
229	1	fd0d3453-050b-4f6b-a462-11ab395201fc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 10:07:11.474951	2026-03-19 10:22:54.807712	2026-03-19 10:07:11.476918
230	1	80cb21d4-3b37-44ae-8679-addbfdf056ab	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 10:22:54.822426	2026-03-19 10:25:07.191475	2026-03-19 10:22:54.824152
231	1	eb341baf-4bec-4d2b-a209-dbfafbfd8e86	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 10:25:07.206226	2026-03-19 13:33:40.077552	2026-03-19 10:25:07.208048
246	1	7d06b319-068a-400f-8b21-04931c72d9e3	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:23:50.561279	2026-03-19 17:26:17.782954	2026-03-19 17:23:50.562835
349	1	a6598f81-8a91-49de-830e-4c5daf9539b2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 15:24:56.84946	2026-03-20 16:21:55.610038	2026-03-20 15:24:56.85005
247	1	108a5dfd-4264-4c47-a5fd-b8afe0dcd1d0	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:26:23.355011	2026-03-19 17:30:26.466052	2026-03-19 17:26:23.35666
248	1	c55609fe-6471-45b7-9044-d397ccdc9fdc	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:30:33.650022	2026-03-19 17:33:04.708904	2026-03-19 17:30:33.651931
249	1	df20c76c-f2bb-4fd4-bc68-3127e6ed5776	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:33:12.629582	2026-03-19 17:42:38.230895	2026-03-19 17:33:12.631028
250	1	82e9d42b-6d80-4010-8f98-8396d8cb0c07	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:42:38.235976	2026-03-19 17:45:49.946214	2026-03-19 17:42:38.237723
251	1	2cc7f405-e86d-4cee-99e7-e929335add14	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:45:58.323644	2026-03-19 17:48:16.046551	2026-03-19 17:45:58.325656
252	1	76ecb664-65db-4e94-a163-f1f7d8592cb8	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:48:24.485691	2026-03-19 17:51:17.684226	2026-03-19 17:48:24.487651
253	1	e66eaf63-5598-41f7-bd26-6456031495a9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:51:27.429399	2026-03-19 17:51:27.560653	2026-03-19 17:51:27.433011
254	1	b67a601b-73c0-41f4-9bbf-6e9159b46d05	WORKSPACE	LOGOUT	\N	\N	2026-03-19 17:51:27.563711	2026-03-19 17:54:23.314699	2026-03-19 17:51:27.56411
255	1	c44ff215-ad14-4ae8-bcd8-e2b0377fb91e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:54:33.502789	2026-03-19 17:57:25.778215	2026-03-19 17:54:33.506655
256	1	a95ad31b-2ed1-4199-9805-6aebbb559163	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 17:57:25.782673	2026-03-19 18:04:37.012823	2026-03-19 17:57:25.784904
257	1	824c9f03-1b84-4f71-b150-83d07d83f7ab	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:04:37.017558	2026-03-19 18:14:03.948225	2026-03-19 18:04:37.019339
258	1	ab6ae325-a623-490e-8403-862a58f8eb84	WORKSPACE	LOGOUT	\N	\N	2026-03-19 18:14:03.952899	2026-03-19 18:16:40.357285	2026-03-19 18:14:03.954528
259	1	01fb800e-806b-4967-88a6-8bb23ca2e090	WORKSPACE	LOGOUT	\N	\N	2026-03-19 18:16:53.271736	2026-03-19 18:18:44.052231	2026-03-19 18:16:53.273485
260	1	c14764c6-3b8a-4a82-9b0f-f9db8a5ea31f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:18:53.093794	2026-03-19 18:37:08.030089	2026-03-19 18:18:53.095699
261	1	6a5861a4-bcb4-4a78-88c3-33c2196b36a1	WORKSPACE	LOGOUT	\N	\N	2026-03-19 18:37:08.034862	2026-03-19 18:39:32.733654	2026-03-19 18:37:08.036458
262	1	187dde57-3ae9-455b-b29f-6a2dcd95b5ab	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:39:40.319534	2026-03-19 18:42:26.013759	2026-03-19 18:39:40.321433
263	1	cb06babd-ef0f-4db9-88c2-b3ea2cbb5f19	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:42:26.019045	2026-03-19 18:45:16.348382	2026-03-19 18:42:26.020481
264	1	bc1ade70-4c30-4bf5-bbd4-2d1f0a7e9efe	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:45:16.36377	2026-03-19 18:59:51.558583	2026-03-19 18:45:16.366077
265	1	bcc311fa-be65-4fd7-8f52-31bdc3a29c49	WORKSPACE	KICKED_OUT	\N	\N	2026-03-19 18:59:51.574193	2026-03-20 08:32:23.331923	2026-03-19 18:59:51.575954
266	1	f439424c-c4b6-44fa-9282-892d35f532dc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 08:32:23.34531	2026-03-20 08:34:57.827996	2026-03-20 08:32:23.348288
267	1	32a9a107-63b1-4539-839f-2d88e0537462	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 08:34:57.83047	2026-03-20 08:35:52.85235	2026-03-20 08:34:57.831204
268	1	d2a75240-b8a9-4930-873c-39b62c9f0a7f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 08:35:52.854265	2026-03-20 08:53:34.241306	2026-03-20 08:35:52.854635
269	1	4411976f-14eb-4583-bd5a-f34a11dc2d5f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 08:53:34.25171	2026-03-20 08:57:04.329422	2026-03-20 08:53:34.252331
270	1	f38836a7-8b3c-432f-845b-36a56d7919db	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 08:57:04.339154	2026-03-20 09:00:22.830195	2026-03-20 08:57:04.339555
271	1	c9c551b6-502e-414c-892b-a31d6ff26213	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:00:22.832064	2026-03-20 09:09:52.557111	2026-03-20 09:00:22.832393
272	1	d03a61f8-e780-4438-bc9a-89ba51d989c9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:09:52.568648	2026-03-20 09:10:08.304429	2026-03-20 09:09:52.569295
273	1	82bfb8c2-80c0-4034-a9f1-5ea09941171d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:10:08.305962	2026-03-20 09:12:32.134593	2026-03-20 09:10:08.306317
274	1	45b5ada5-cafa-4adb-aff7-72a1c0ae5ffc	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:12:32.136428	2026-03-20 09:14:10.700357	2026-03-20 09:12:32.136965
275	1	031a152f-45b2-4c68-8c5d-33abcd483758	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:14:10.701721	2026-03-20 09:15:42.45146	2026-03-20 09:14:10.70203
276	1	53b0c3d9-d60a-4f44-9b64-3e3d99f3f2c9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:15:42.453194	2026-03-20 09:17:35.759156	2026-03-20 09:15:42.453496
277	1	09e45fc0-1862-4ffe-984a-6d578cd535e0	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:17:35.769829	2026-03-20 09:17:48.897029	2026-03-20 09:17:35.77045
278	1	44368d42-b249-4819-8264-fb6636d52719	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:17:48.899594	2026-03-20 09:18:01.544415	2026-03-20 09:17:48.900164
279	1	e4a51f05-bc9d-4030-b01f-451d665b930c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:18:01.545709	2026-03-20 09:18:10.225169	2026-03-20 09:18:01.546034
280	1	00b135f0-7ca7-4714-af91-068cda18d756	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:18:10.226695	2026-03-20 09:22:03.008567	2026-03-20 09:18:10.227016
281	1	b4e92fe2-f848-43fa-a594-ca5c6e998ae7	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:22:03.019821	2026-03-20 09:22:20.793022	2026-03-20 09:22:03.020378
282	1	5578b35c-b51d-4f1c-b545-e1c7d6b468bf	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:22:20.794704	2026-03-20 09:23:58.202742	2026-03-20 09:22:20.795017
283	1	ae04dadc-b79d-4896-abab-c8f8b0811c22	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:23:58.213064	2026-03-20 09:24:24.394106	2026-03-20 09:23:58.213507
284	1	70db3566-e337-4a46-ae75-6d07da3d16a0	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:24:24.395961	2026-03-20 09:25:52.387698	2026-03-20 09:24:24.396304
285	1	e0e7cf95-406c-48c8-8d9a-eed15250a66f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:25:52.389044	2026-03-20 09:26:03.273736	2026-03-20 09:25:52.389336
286	1	2f77b5a6-663d-4979-9661-ff5e86549e06	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:26:03.275564	2026-03-20 09:27:56.223108	2026-03-20 09:26:03.27607
287	1	8739e660-096a-4d9e-9fd6-5c15b0963288	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:27:56.225441	2026-03-20 09:28:15.639836	2026-03-20 09:27:56.225797
288	1	fe9605a6-aa4a-4531-abf4-44934feb3a2f	WORKSPACE	LOGOUT	\N	\N	2026-03-20 09:28:15.641814	2026-03-20 09:29:26.948493	2026-03-20 09:28:15.642262
289	1	d13334cf-c46f-4977-9b6d-b40fbf118c85	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:29:44.695641	2026-03-20 09:31:39.972792	2026-03-20 09:29:44.695964
290	1	88e5d42e-920c-4d94-9b71-db6dbe5f8aa9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:31:39.982723	2026-03-20 09:35:51.715038	2026-03-20 09:31:39.983279
291	1	5269c078-1cd6-4e46-b797-93e6abe65a47	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:35:51.717493	2026-03-20 09:36:07.425836	2026-03-20 09:35:51.718044
292	1	b04d2db7-f201-48f8-8b53-93b88fa3a72d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:36:07.43681	2026-03-20 09:36:35.962251	2026-03-20 09:36:07.437407
293	1	8a4f61b7-568b-49ed-8939-81caa9c83bf5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:36:35.972213	2026-03-20 09:37:51.444378	2026-03-20 09:36:35.972775
294	1	f5ad2614-2087-45b5-b588-0cc24ee2da79	WORKSPACE	LOGOUT	\N	\N	2026-03-20 09:37:51.446528	2026-03-20 09:37:55.871528	2026-03-20 09:37:51.446852
295	1	f3a36e73-9aa7-487a-b1e3-7b61551a59f8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 09:47:51.830267	2026-03-20 10:10:19.039467	2026-03-20 09:47:51.830579
296	1	c9dcaf43-7162-4ad5-ab42-c7bf5d5147cc	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:10:19.050944	2026-03-20 10:10:31.968902	2026-03-20 10:10:19.051348
297	1	d2be728a-fdfe-4a8b-8779-089da8d82b79	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:10:42.461534	2026-03-20 10:12:15.098393	2026-03-20 10:10:42.461833
298	1	a8ff2629-8aba-42c1-9196-8304312f8f50	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:12:15.10901	2026-03-20 10:12:24.316495	2026-03-20 10:12:15.109379
299	1	73a94212-705b-495d-8738-0258142b1f2d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:12:24.319594	2026-03-20 10:14:22.382227	2026-03-20 10:12:24.320139
300	1	373d7742-6029-4f17-92c2-23b13f2e8263	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:14:22.383694	2026-03-20 10:17:11.559598	2026-03-20 10:14:22.384031
301	1	def015d1-417e-4d49-bb94-bfbd9c4eb6fd	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:17:11.569667	2026-03-20 10:18:06.881893	2026-03-20 10:17:11.570258
302	1	8de4e7be-df1b-4044-8f07-174302fc3339	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:18:11.729113	2026-03-20 10:18:11.818604	2026-03-20 10:18:11.729413
303	1	9411b411-2917-4c71-9ff9-a00bc29a904f	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:18:11.820943	2026-03-20 10:18:17.097959	2026-03-20 10:18:11.821286
305	1	8e082616-772c-482d-85fa-1fb48e5a3055	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:19:03.312154	2026-03-20 10:32:13.916675	2026-03-20 10:19:03.312457
306	1	bb30475f-b0c3-4d5c-9a03-1c29dd2fc7db	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:32:13.918402	2026-03-20 10:39:44.739931	2026-03-20 10:32:13.918808
351	1	61870527-5a62-472d-8303-c9818dcb00fa	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 16:21:55.611495	2026-03-20 17:01:35.164964	2026-03-20 16:21:55.611849
307	1	96ac84ff-0ada-4186-aee4-ab9510854089	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:39:44.741726	2026-03-20 10:41:16.343966	2026-03-20 10:39:44.742049
311	1	cdee031d-7caa-435d-a748-665f42050fc5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:42:31.236354	2026-03-20 10:42:43.281633	2026-03-20 10:42:31.23666
354	1	8d92ada5-4442-4aee-bf53-f0b28ea36d2e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 17:17:36.909437	2026-03-20 17:52:36.482179	2026-03-20 17:17:36.910987
315	1	57d353c6-f229-43f4-8dc7-c989cc0b5c65	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:44:36.537841	2026-03-20 10:46:34.577995	2026-03-20 10:44:36.538162
318	1	f6302783-d82f-4d92-820f-20f44cc1f582	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:48:05.549605	2026-03-20 10:48:56.855651	2026-03-20 10:48:05.549938
356	1	e3d697a6-ab4e-4c1a-9cb0-e09cf7089cf7	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 18:02:29.188767	2026-03-20 18:12:40.725724	2026-03-20 18:02:29.189476
319	1	b996906f-8060-40a6-800c-6ea13e124c19	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:49:11.452334	2026-03-20 10:49:22.96998	2026-03-20 10:49:11.452636
321	1	216c4a43-d61e-428f-95b5-7fbae67c17ae	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:50:18.724431	2026-03-20 10:51:42.326379	2026-03-20 10:50:18.724734
357	1	32d11f12-e984-4788-a337-cdc25022859a	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 18:12:40.727837	2026-03-20 18:13:09.430137	2026-03-20 18:12:40.728231
325	1	88503f94-f1fc-49dc-b9d0-5a99ebb62436	WORKSPACE	LOGOUT	\N	\N	2026-03-20 11:00:44.634071	2026-03-20 11:00:51.581629	2026-03-20 11:00:44.634656
326	1	9e2d38d6-d089-4f3d-a7bd-d08c5c47516d	WORKSPACE	LOGOUT	\N	\N	2026-03-20 11:00:57.04944	2026-03-20 11:01:41.198301	2026-03-20 11:00:57.049747
358	1	eb7b4e22-648b-4434-869e-93ad661d75b2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 18:13:09.432133	2026-03-20 18:26:10.667009	2026-03-20 18:13:09.432526
377	1	f5792f82-de4e-4b78-8a8d-dfd5b7ad2137	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 17:00:22.132645	2026-03-25 17:00:29.948118	2026-03-25 17:00:22.133273
380	1	87329619-1c87-4a57-8585-65dcace8eabe	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 20:18:56.244989	2026-03-25 20:47:16.321522	2026-03-25 20:18:56.245642
382	1	88281001-8aa6-4cce-a80f-e9487bc22ae3	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 20:47:16.323005	2026-03-25 20:51:02.061251	2026-03-25 20:47:16.323384
383	1	1090826e-abc0-4d69-a717-641c6c18b43e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 20:51:02.062725	2026-03-25 21:03:36.424887	2026-03-25 20:51:02.063134
386	1	31a9da7f-5d3a-4f7c-9ed6-20b02640b458	DESKTOP	KICKED_OUT	\N	\N	2026-03-25 21:47:19.475156	2026-03-25 21:47:52.906035	2026-03-25 21:47:19.47554
387	1	4a2e7497-1757-4c8c-b8d7-d7636313c361	DESKTOP	KICKED_OUT	\N	\N	2026-03-25 21:47:52.920434	2026-03-25 21:48:43.779119	2026-03-25 21:47:52.920847
388	1	72e10b9c-e693-47dd-ac72-6163b660f091	DESKTOP	KICKED_OUT	\N	\N	2026-03-25 21:48:43.79276	2026-03-28 10:36:34.438659	2026-03-25 21:48:43.793121
389	1	71eb95ae-c9f2-48c7-b31c-62b38aabb957	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 10:36:34.462392	2026-03-28 10:37:19.366712	2026-03-28 10:36:34.465494
391	1	7f048e4a-cc85-4c56-8091-47a9c3ab3e7a	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:36:18.584337	2026-03-28 11:37:37.092453	2026-03-28 11:36:18.586515
394	1	1c45efc1-f1a6-4a39-be70-db27093d8c44	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:41:51.389475	2026-03-28 11:43:02.941911	2026-03-28 11:41:51.391544
397	1	435b540a-baa3-4d1f-b0f8-433eda3722eb	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:47:41.895934	2026-03-28 11:49:29.618562	2026-03-28 11:47:41.898128
398	1	b897b227-aa6f-4f3c-bdb5-d2be211e50c1	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:49:29.637685	2026-03-28 11:51:55.991603	2026-03-28 11:49:29.639466
400	1	54f10007-139f-48f5-a644-469a05e8455a	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:54:17.512503	2026-03-28 11:54:47.205682	2026-03-28 11:54:17.514364
402	1	df217f8f-682c-4240-b047-8d40eb17ba6c	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:57:17.119507	2026-03-28 11:57:33.700979	2026-03-28 11:57:17.121682
403	1	fb690fce-14e4-4af9-9114-8e6112e69887	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 11:57:33.717621	2026-03-28 12:05:29.169433	2026-03-28 11:57:33.717994
405	1	509f92d7-f714-4cc9-b661-848713dacacf	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:11:16.385747	2026-03-28 12:11:22.501235	2026-03-28 12:11:16.387888
410	1	e5e083f5-0609-4f9d-ab7d-6bc7b639575d	DESKTOP	LOGOUT	\N	\N	2026-03-28 14:47:00.814053	2026-03-28 14:47:48.032551	2026-03-28 14:47:00.815929
411	1	3ad0ff02-8efb-4483-acc9-7e0d7bdc5883	DESKTOP	LOGOUT	\N	\N	2026-03-28 14:48:08.52237	2026-03-28 14:50:20.363045	2026-03-28 14:48:08.522986
412	3	6fb448bf-7e90-46ae-ba70-242f280edf68	DESKTOP	LOGOUT	\N	\N	2026-03-28 14:50:29.632591	2026-03-28 14:53:20.242771	2026-03-28 14:50:29.633104
404	1	1f094967-f438-4770-98ee-51f3d4f20212	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:05:29.186896	2026-03-28 15:04:36.105553	2026-03-28 12:05:29.187291
413	1	bac97042-6643-4dfe-a436-ce3424857fda	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 14:53:26.273435	2026-03-28 15:06:19.307076	2026-03-28 14:53:26.273911
414	1	490a6a67-cfe9-4696-ac6c-c70c6ce4e297	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 15:06:19.326261	2026-03-28 15:07:14.694347	2026-03-28 15:06:19.326946
415	1	8ce66315-6bfc-4726-b1d3-643a1ee1a004	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 15:07:14.712649	2026-03-28 15:07:55.566702	2026-03-28 15:07:14.713431
417	3	5f09381c-c99e-4465-8f9c-9d565d47c160	MOBILE	KICKED_OUT	\N	\N	2026-03-28 15:11:44.037893	2026-03-28 15:12:01.416984	2026-03-28 15:11:44.038945
418	3	55ded117-e081-4efb-b539-544df53a32ff	MOBILE	KICKED_OUT	\N	\N	2026-03-28 15:12:01.434086	2026-03-28 15:12:25.091758	2026-03-28 15:12:01.434642
390	1	bfd5d977-1be8-418e-8035-c22960c55227	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 10:37:19.384367	2026-03-28 15:16:51.126037	2026-03-28 10:37:19.385079
381	3	e26ffe75-d0b7-43ce-8b19-44095792b616	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 20:21:28.123526	2026-03-28 15:17:01.474102	2026-03-25 20:21:28.123928
416	1	7ebcd648-6d57-4660-a94f-e5138847e662	DESKTOP	EXPIRED	\N	\N	2026-03-28 15:07:55.582468	\N	2026-03-28 15:07:55.582903
406	1	63316bd4-2d50-450f-9210-5fd4c04843d2	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:11:22.518014	2026-03-28 15:19:55.822492	2026-03-28 12:11:22.518389
407	1	74e0b3ea-f544-426e-bcef-382f7140f809	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:17:30.891015	2026-03-28 15:19:57.576771	2026-03-28 12:17:30.893893
408	1	08d210ac-c192-4a08-ba24-faa425946bd9	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:18:35.068883	2026-03-28 15:19:59.06249	2026-03-28 12:18:35.072322
409	1	f11e73af-456e-459a-9156-ef0310df6d77	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 12:40:24.800457	2026-03-28 15:20:00.615406	2026-03-28 12:40:24.802557
419	1	2cdc3c6b-72d4-45b7-bcfe-46ebe4b1d211	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 15:19:32.770928	2026-03-28 15:22:52.701885	2026-03-28 15:19:32.774295
350	5	d62abb8d-1dbd-48a7-bdf2-c385926b82bd	WORKSPACE	EXPIRED	\N	\N	2026-03-20 16:21:41.589538	2026-03-28 15:28:33.845605	2026-03-20 16:21:41.589923
392	1	20121e35-907d-4af0-bab9-b9e7ead3ac7f	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:37:37.111594	2026-03-28 15:28:33.84317	2026-03-28 11:37:37.112002
393	1	11627cdc-70b9-4d23-a036-793ee49a4906	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:40:07.970793	2026-03-28 15:28:33.842804	2026-03-28 11:40:07.97289
395	1	1cf5f14c-e7c0-4f0e-ba13-1efaaa66607a	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:43:02.958472	2026-03-28 15:28:33.842316	2026-03-28 11:43:02.958843
396	1	b1990d61-4e28-4ad2-ae8c-d7438a7583f0	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:46:46.313616	2026-03-28 15:28:33.841568	2026-03-28 11:46:46.315567
399	1	dbcb3ecc-6cae-4927-a518-e1ee3a05d72e	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:51:56.007241	2026-03-28 15:28:33.840944	2026-03-28 11:51:56.007667
401	1	5d97e18d-af24-4771-bbfe-e1a604c1489e	DESKTOP	EXPIRED	\N	\N	2026-03-28 11:54:47.224853	2026-03-28 15:28:33.840422	2026-03-28 11:54:47.225531
421	1	a1971ea8-ba0a-47e8-a594-2a03c2a15e6f	MOBILE	KICKED_OUT	\N	\N	2026-03-28 15:44:16.209786	2026-03-28 15:52:13.926219	2026-03-28 15:44:16.212179
420	1	e327332b-39f1-40e0-9464-8b12416a93e0	DESKTOP	EXPIRED	\N	\N	2026-03-28 15:22:52.720693	\N	2026-03-28 15:22:52.721459
422	1	5c268372-7788-415a-b362-fda7c69e1043	MOBILE	EXPIRED	\N	\N	2026-03-28 15:52:13.94487	2026-03-28 16:12:48.227323	2026-03-28 15:52:13.945534
423	1	ebda65bf-86ea-4380-a0a9-cd7f0a6bcd13	DESKTOP	EXPIRED	\N	\N	2026-03-28 16:11:54.848995	\N	2026-03-28 16:11:54.851622
426	1	aa6d8c25-dbfd-4b16-8426-dc70edf9d676	DESKTOP	EXPIRED	\N	\N	2026-03-28 16:58:14.797932	\N	2026-03-28 16:58:14.801122
427	1	d5f5c90d-e2ae-4ba7-8656-677baa90d551	DESKTOP	EXPIRED	\N	\N	2026-03-28 17:45:23.464334	\N	2026-03-28 17:45:23.466928
424	1	dae928a0-2611-438c-b68d-a4f86ff91359	MOBILE	EXPIRED	\N	\N	2026-03-28 16:12:34.475247	2026-03-28 19:19:30.994716	2026-03-28 16:12:34.476075
308	1	e9ecb452-e151-4505-9cd6-e3c4b55f25ae	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:41:19.934858	2026-03-20 10:41:35.594242	2026-03-20 10:41:19.935181
348	1	90c2735c-664b-407c-94c9-e267331f6711	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 15:24:18.121203	2026-03-20 15:24:56.847105	2026-03-20 15:24:18.121595
309	1	e24e942a-04c0-426e-909a-8d8a8a2f0c30	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:41:35.596087	2026-03-20 10:41:50.469256	2026-03-20 10:41:35.5964
310	1	276b40f7-cce2-4b69-9b99-9bc18ffd4de2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:41:50.479052	2026-03-20 10:42:31.234807	2026-03-20 10:41:50.479508
352	1	2c88804f-4fd1-4d67-8fdd-f427f49ad36c	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 17:01:35.172006	2026-03-20 17:07:14.035504	2026-03-20 17:01:35.173631
312	1	e2fb108a-8ca5-4dc8-9683-1ea3bb805e6d	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:42:43.283326	2026-03-20 10:43:24.131808	2026-03-20 10:42:43.283637
313	1	82c594e9-609b-4dd2-9e88-bf51e96b00cd	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:43:27.48862	2026-03-20 10:43:39.290148	2026-03-20 10:43:27.488949
353	1	37e571b4-eada-488e-afe2-277b0a13147d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 17:07:14.037135	2026-03-20 17:17:36.905626	2026-03-20 17:07:14.037554
314	1	6cd8f2db-9eb7-464e-a57a-b854cc952290	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:43:39.291741	2026-03-20 10:44:36.536269	2026-03-20 10:43:39.292063
316	1	b0008dd0-a7a3-44e2-8fb7-e266de9448ad	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:46:34.588565	2026-03-20 10:47:48.550233	2026-03-20 10:46:34.589047
355	1	43e110bf-704f-43eb-a497-e28f5e7c7338	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 17:52:36.487408	2026-03-20 18:02:29.185497	2026-03-20 17:52:36.489418
317	1	6234cf86-950c-404b-ab5d-43437619dc83	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:47:52.829327	2026-03-20 10:48:00.09373	2026-03-20 10:47:52.829624
320	1	564eee69-ebff-404c-bf27-84d56f426f55	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:49:22.97149	2026-03-20 10:50:18.722577	2026-03-20 10:49:22.971802
359	1	06dc5936-96a6-4f51-b8ca-90f9a5426977	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 18:26:10.669022	2026-03-25 10:15:23.243165	2026-03-20 18:26:10.66966
322	1	4634cec1-a84e-4c9e-b217-f232e57ca474	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:51:42.328234	2026-03-20 10:52:43.539416	2026-03-20 10:51:42.328527
323	1	274274f1-7548-4c37-a208-2b18b0902013	WORKSPACE	LOGOUT	\N	\N	2026-03-20 10:52:43.541532	2026-03-20 10:54:44.596949	2026-03-20 10:52:43.541837
360	1	7bb4f014-3491-4462-9fda-410b1e2281e9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 10:15:23.250427	2026-03-25 11:28:09.62079	2026-03-25 10:15:23.252308
324	1	cdcf0916-24b6-4764-b520-93d4160873ab	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:54:49.071569	2026-03-20 11:00:44.623042	2026-03-20 10:54:49.07207
327	1	75e5cb08-587b-4774-841f-6e8b4a1f85a2	WORKSPACE	LOGOUT	\N	\N	2026-03-20 11:01:44.882534	2026-03-20 11:02:47.271279	2026-03-20 11:01:44.882837
361	1	58f7c4ed-65a8-454b-be2c-e070f8bf76fb	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:28:09.627914	2026-03-25 11:37:07.802848	2026-03-25 11:28:09.629366
328	1	3f0d729b-7479-41e6-94e2-ea743913fa99	WORKSPACE	LOGOUT	\N	\N	2026-03-20 11:02:51.722644	2026-03-20 11:03:40.917272	2026-03-20 11:02:51.722971
329	1	c4ca796b-865a-4abe-b175-f5144c1116a7	WORKSPACE	LOGOUT	\N	\N	2026-03-20 11:03:45.596884	2026-03-20 11:06:17.283096	2026-03-20 11:03:45.597185
362	1	293d94e7-963b-49c9-9158-cb8138fcdf93	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:37:07.804386	2026-03-25 11:37:16.42612	2026-03-25 11:37:07.80489
330	1	d0cceab5-567b-4a88-ab56-6db0b0bce0d5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 11:07:59.690442	2026-03-20 11:09:16.957501	2026-03-20 11:07:59.690851
331	1	583e4afd-a37b-4db8-be5f-a40d65bf2dd8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 11:09:16.959424	2026-03-20 11:09:47.647805	2026-03-20 11:09:16.95979
304	3	f33c3507-a515-4bdf-a423-c75de13852e2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 10:18:24.355897	2026-03-25 11:37:22.212556	2026-03-20 10:18:24.356192
332	1	068a44ed-3481-4892-bef8-6f6a966e99a5	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 11:09:47.649514	2026-03-20 11:14:52.123229	2026-03-20 11:09:47.649826
333	1	1a37d078-3309-4f92-9d49-6d3353ad7d3e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 11:14:52.13394	2026-03-20 12:15:19.891809	2026-03-20 11:14:52.134499
363	1	a56433a6-e811-4865-8cdb-536c042086ad	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:37:16.427992	2026-03-25 11:38:14.404452	2026-03-25 11:37:16.428391
334	1	64088347-c222-438a-a98d-84de71141db9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:15:19.90186	2026-03-20 12:19:40.124838	2026-03-20 12:15:19.902404
335	1	645e277b-a450-48c4-81a3-d54dad988642	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:19:40.13536	2026-03-20 12:26:47.421574	2026-03-20 12:19:40.135856
365	1	4959a666-89ee-4d2d-b9e7-1de267b61bf8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:38:14.40637	2026-03-25 11:39:02.405309	2026-03-25 11:38:14.406734
336	1	15655f49-f9ac-4233-924c-c5f84ebc0622	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:26:47.432214	2026-03-20 12:31:57.912736	2026-03-20 12:26:47.43278
337	1	3b3d53af-2214-4d33-9aff-4c7b1647413f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:31:57.914874	2026-03-20 12:43:56.231979	2026-03-20 12:31:57.915185
366	1	07205f22-31d2-4cff-8230-82bab8d74436	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:39:02.407091	2026-03-25 11:39:12.4276	2026-03-25 11:39:02.407452
338	1	4757bb3b-e2c8-4e74-98f4-fdadf8949ad2	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:43:56.233469	2026-03-20 12:45:03.587219	2026-03-20 12:43:56.233774
339	1	2e97ab3f-d282-449a-9300-a2b6b997b8ca	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:45:03.588569	2026-03-20 12:49:01.29722	2026-03-20 12:45:03.588885
364	3	d1454c04-f06c-421d-9be8-71a8b2de660b	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:37:22.214388	2026-03-25 11:42:29.200524	2026-03-25 11:37:22.214986
340	1	e35e782a-ecb7-4c53-b697-7be0b4b7c21e	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:49:01.299927	2026-03-20 12:55:19.246985	2026-03-20 12:49:01.300438
341	1	d6a6e71b-8489-4cef-8f36-eb0339f3cac0	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:55:19.248494	2026-03-20 12:59:53.453638	2026-03-20 12:55:19.248874
367	1	6be53425-d8a6-4264-a732-83e65d036d5f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:39:12.429394	2026-03-25 11:57:26.429868	2026-03-25 11:39:12.429755
342	1	947831ed-77c5-4343-aa4a-2663324c8478	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 12:59:53.45866	2026-03-20 13:22:00.735657	2026-03-20 12:59:53.460588
343	1	b31cced6-0eef-4bf8-bf3c-8e8e463d5da7	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 13:22:00.738117	2026-03-20 13:22:51.144998	2026-03-20 13:22:00.738618
369	1	8769b00c-9331-43d4-bfae-5195d169f5e6	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:57:26.431526	2026-03-25 13:05:10.629625	2026-03-25 11:57:26.432016
344	1	2262d407-8ce7-4dfd-8054-072898cce642	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 13:22:51.147346	2026-03-20 13:25:37.529053	2026-03-20 13:22:51.14778
345	1	32a6a62d-794a-4739-95a5-944f8e87d9ce	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 13:25:37.53173	2026-03-20 14:17:08.737496	2026-03-20 13:25:37.532545
370	1	e410eec4-67c6-4a8a-830b-8d6a6bdb42ae	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 13:05:10.636998	2026-03-25 13:07:21.167458	2026-03-25 13:05:10.63901
346	1	9d1ad2d5-d1f0-4d6c-b273-e92f4f83c58d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 14:17:08.742076	2026-03-20 14:43:57.255253	2026-03-20 14:17:08.744527
347	1	ce9218d6-f671-4e49-8a85-77379e563e40	WORKSPACE	KICKED_OUT	\N	\N	2026-03-20 14:43:57.261891	2026-03-20 15:24:18.119347	2026-03-20 14:43:57.263622
371	1	32ce0a4e-4f93-445e-8506-0508c53e9042	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 13:07:21.168926	2026-03-25 13:30:30.916507	2026-03-25 13:07:21.169335
372	1	661beaf7-eb91-4739-8749-cf32cd6ded50	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 13:30:30.918408	2026-03-25 15:12:30.565782	2026-03-25 13:30:30.919076
373	1	2017e4f4-f7a9-4d47-a0e2-3c23487d2114	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 15:12:30.580109	2026-03-25 15:15:33.088856	2026-03-25 15:12:30.581974
374	1	447be27a-31d6-475f-988d-720d9967de40	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 15:15:33.090496	2026-03-25 16:55:27.007087	2026-03-25 15:15:33.090932
375	1	f7ae89af-1946-44b3-b5d1-1c9e93a44f6f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 16:55:27.024361	2026-03-25 16:57:13.76351	2026-03-25 16:55:27.02606
376	1	71e68817-3628-4515-9268-5edd53c55f89	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 16:57:13.765082	2026-03-25 17:00:22.129208	2026-03-25 16:57:13.765495
378	1	643b57d5-c167-4673-a3f2-d2ea330ff01f	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 17:00:29.949577	2026-03-25 20:17:38.421111	2026-03-25 17:00:29.949967
379	1	b7d35d4c-5a17-45f6-a27b-373b946b1ab9	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 20:17:38.436535	2026-03-25 20:18:56.241117	2026-03-25 20:17:38.438768
368	3	3e5c5d97-afa9-4468-bf64-d6172a9ffb1d	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 11:42:29.2023	2026-03-25 20:21:28.121467	2026-03-25 11:42:29.202657
385	1	10b0659e-653c-4087-bc1d-4fa6496d403e	DESKTOP	KICKED_OUT	\N	\N	2026-03-25 21:47:11.87961	2026-03-25 21:47:19.459427	2026-03-25 21:47:11.882334
384	1	6dc12995-e753-406d-9c7a-b4dca25607b8	WORKSPACE	KICKED_OUT	\N	\N	2026-03-25 21:03:36.42636	2026-03-28 15:17:08.33557	2026-03-25 21:03:36.426712
428	1	acae3741-b0d8-4013-8983-c75c756e0279	DESKTOP	EXPIRED	\N	\N	2026-03-28 18:09:02.563601	\N	2026-03-28 18:09:02.565708
429	1	86604476-de63-4f5e-b519-5620244db21f	DESKTOP	LOGOUT	\N	\N	2026-03-28 18:20:33.858787	2026-03-28 19:16:46.567335	2026-03-28 18:20:33.860278
430	3	b92104cb-70b8-4df5-9e44-a002ba5a8b50	DESKTOP	KICKED_OUT	\N	\N	2026-03-28 19:16:52.519092	2026-03-28 19:17:29.493623	2026-03-28 19:16:52.51958
425	3	217c43d5-6917-4f95-9167-a441deefd6a2	MOBILE	EXPIRED	\N	\N	2026-03-28 16:20:16.603103	2026-03-28 19:19:30.994578	2026-03-28 16:20:16.604186
432	1	6d99a7a7-5e7c-45b7-9bf3-896104b1ea09	DESKTOP	LOGOUT	\N	\N	2026-03-28 19:19:14.426873	2026-03-29 08:30:59.965008	2026-03-28 19:19:14.427336
463	1	71dac547-ffac-4faa-9ff1-98cd60bff7b8	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 09:18:43.108322	2026-04-03 13:13:45.928543	2026-04-03 13:13:45.905855
433	1	d4d695ef-b56b-4553-8ddf-ce3a1fc45582	DESKTOP	EXPIRED	\N	\N	2026-03-29 08:31:13.287289	\N	2026-03-29 08:31:13.288693
434	3	b402f69d-f6e5-4bd6-9797-0b843a3f527c	MOBILE	EXPIRED	\N	\N	2026-03-29 08:35:07.932816	\N	2026-03-29 08:35:07.933278
435	1	4f191388-09b1-434a-8dd4-466cb4f00fd0	DESKTOP	EXPIRED	\N	\N	2026-03-29 10:22:05.773913	\N	2026-03-29 10:22:05.777184
431	3	142f97e5-50f7-4b72-92a1-240493de0bcb	DESKTOP	EXPIRED	\N	\N	2026-03-28 19:17:29.508095	2026-03-29 10:50:55.109742	2026-03-28 19:17:29.508346
436	1	40044183-06c4-4a9f-8360-aae477ceacc4	DESKTOP	EXPIRED	\N	\N	2026-03-29 10:28:30.203849	\N	2026-03-29 10:28:30.205416
461	1	8f733ca9-1390-464e-9222-7b4cb6b15fd9	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-02 22:09:10.61582	2026-04-02 22:45:31.295024	2026-04-02 22:45:31.230734
437	1	9693d74b-f93f-40f7-822b-f1af9649b568	DESKTOP	EXPIRED	\N	\N	2026-03-29 14:45:20.84387	\N	2026-03-29 14:45:20.845647
452	1	242dd4b3-3761-410e-912d-c8c2b81d990e	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:56:45.324606	2026-04-02 21:54:43.733992	2026-04-02 20:56:45.325268
438	1	19e84a4e-d16b-457c-a742-80b9b7ead544	DESKTOP	EXPIRED	\N	\N	2026-03-29 16:24:07.885218	\N	2026-03-29 16:24:07.886772
439	1	34d685ae-8902-4fb2-b53d-d8c86fb88f31	DESKTOP	EXPIRED	\N	\N	2026-03-29 16:42:02.649538	\N	2026-03-29 16:42:02.651021
440	1	16de8c28-76d3-4f4b-b603-27758c33a265	DESKTOP	LOGOUT	\N	\N	2026-03-29 19:11:31.782086	2026-03-29 19:11:47.842454	2026-03-29 19:11:31.783887
477	1	e97c014a-9866-4f3f-bdef-0b6098ab7af6	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-03 17:37:09.59007	2026-04-03 17:52:52.719119	2026-04-03 17:52:15.830801
441	1	0cc6bbb4-301d-43bf-920d-2f20b846b908	DESKTOP	EXPIRED	\N	\N	2026-03-29 19:12:00.803902	\N	2026-03-29 19:12:00.80446
443	1	a634ea27-d757-486d-86be-ef20068d2012	DESKTOP	LOGOUT	\N	\N	2026-04-02 18:08:52.509865	2026-04-02 18:54:17.973631	2026-04-02 18:08:52.549873
445	1	d63c2204-2f74-4ab9-a806-5f68408d1eda	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 19:39:51.832675	2026-04-02 19:40:08.717702	2026-04-02 19:39:51.834255
446	1	9688210e-cd7a-4c7f-a686-0d28d99ec7a5	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 19:40:08.719434	2026-04-02 20:35:11.040393	2026-04-02 19:40:08.719829
448	3	94097c74-568b-4ad2-b26d-96f889630dd5	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:35:31.499212	2026-04-02 20:44:33.463081	2026-04-02 20:35:31.499584
447	1	d352714c-5850-4e5d-ba77-8f75c5deebed	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:35:11.05083	2026-04-02 20:44:41.957516	2026-04-02 20:35:11.051553
450	1	bb424895-119b-4092-b0a9-a1e43a5cc900	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:44:41.959797	2026-04-02 20:48:07.258414	2026-04-02 20:44:41.960161
451	1	cce5aafa-3cc4-4401-a655-594475f5cdf6	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:48:07.268781	2026-04-02 20:56:45.314393	2026-04-02 20:48:07.269245
444	1	5d054014-de49-4b0b-800d-bbdf92f31d1a	DESKTOP	KICKED_OUT	\N	\N	2026-04-02 18:54:33.587062	2026-04-02 21:10:07.710187	2026-04-02 18:54:33.587617
453	1	40cd6641-d64a-41f6-abf9-92d22961b18c	DESKTOP	LOGOUT	\N	\N	2026-04-02 21:10:07.731919	2026-04-02 21:10:10.696403	2026-04-02 21:10:07.734179
454	3	2bb5d85b-a995-4851-9c4e-f0917938eed0	DESKTOP	LOGOUT	\N	\N	2026-04-02 21:10:27.449226	2026-04-02 21:10:29.646301	2026-04-02 21:10:27.449775
455	1	31aee9f0-de22-439c-a937-d96edd90b99a	DESKTOP	LOGOUT	\N	\N	2026-04-02 21:10:36.951722	2026-04-02 21:10:41.042645	2026-04-02 21:10:36.952226
442	1	aef123d5-3c8a-4bd7-aa68-861e75af47e4	DESKTOP	EXPIRED	\N	\N	2026-03-29 19:26:41.260915	2026-04-02 21:22:49.64991	2026-03-29 19:26:41.265057
456	1	859e7ec4-4984-483a-81f1-43cb9d55fa20	DESKTOP	LOGOUT	\N	\N	2026-04-02 21:22:41.869076	2026-04-02 21:34:14.939111	2026-04-02 21:22:41.86956
457	1	6dfed12a-3f96-4c3c-9052-d8605b45fb1b	DESKTOP	KICKED_OUT	\N	\N	2026-04-02 21:38:28.806967	2026-04-02 21:49:22.567582	2026-04-02 21:38:28.807458
449	3	fd05ce42-a03d-43f2-97af-69700a3a69ae	WORKSPACE	KICKED_OUT	\N	\N	2026-04-02 20:44:33.464844	2026-04-02 21:54:47.495066	2026-04-02 20:44:33.465214
458	1	1f5b600c-b73a-472b-bc14-c0d60826fc89	DESKTOP	EXPIRED	\N	\N	2026-04-02 21:49:37.963241	\N	2026-04-02 22:06:49.056384
467	1	97858ab4-d76b-4e9b-9321-0192b1542246	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 13:46:32.081026	2026-04-03 13:49:24.000333	2026-04-03 13:49:23.989974
464	3	92f30692-baa6-4954-b29d-5ddfe6203233	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-03 13:10:53.816946	2026-04-03 13:49:47.049373	2026-04-03 13:49:47.029481
459	1	6c603265-706b-494b-9580-6df4f1bb3060	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-02 22:07:16.68327	2026-04-02 22:07:47.921361	2026-04-02 22:07:47.898739
460	1	be2297df-73ec-44cc-b082-b777be47d6f0	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-02 22:07:55.191248	2026-04-02 22:09:05.024856	2026-04-02 22:09:05.002852
462	1	20d64b4d-3676-459b-a331-0eaf84c0ff90	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-02 22:45:43.921593	\N	2026-04-03 09:13:30.493404
465	1	2c704d09-568d-4277-ad39-c4540a9a946a	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 13:14:01.25894	2026-04-03 13:18:43.853896	2026-04-03 13:18:43.840878
469	1	cc8e88c6-e6a2-4a93-8efd-17c871a8e803	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 13:51:26.346691	2026-04-03 14:06:27.454537	2026-04-03 14:06:27.441721
466	1	58ead5fa-3dd1-4723-9da8-9c2083cd8bf5	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 13:31:39.746444	2026-04-03 13:40:28.791961	2026-04-03 13:40:28.77001
470	1	c4de04c7-3e53-4e0e-8839-92a4d09af74b	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:06:34.540352	2026-04-03 14:06:42.006805	2026-04-03 14:06:41.993888
471	1	cc2d72f8-f24d-408c-87f8-aee0a8739176	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:06:51.282599	2026-04-03 14:07:08.290476	2026-04-03 14:07:08.269394
472	1	5bd692eb-85f7-427d-a5a7-5f3d06f25778	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:07:17.259792	2026-04-03 14:08:45.996646	2026-04-03 14:08:45.979956
468	1	0111d809-ab23-4459-9437-cdca1838c39a	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-03 13:51:16.892954	2026-04-03 14:10:32.461694	2026-04-03 14:10:32.440391
488	1	76136808-f980-4970-9e40-b5ed5c324a9e	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-09 09:29:11.732149	2026-04-09 15:34:06.383245	2026-04-09 11:53:15.689415
473	1	53d58454-e1f1-42fa-9574-e5ec521d869d	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:10:11.979357	2026-04-03 14:10:14.007269	2026-04-03 14:10:13.986283
512	1	e8a363c1-b8aa-4f8c-998c-f15d478b62f1	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-18 17:54:58.301679	2026-04-21 22:06:58.974455	2026-04-18 17:55:03.794377
482	3	719c5379-504b-4886-a1da-e341eeb28370	MOBILE	EXPIRED	Mozilla/5.0 (Android 13; Mobile; rv:149.0) Gecko/149.0 Firefox/149.0	172.18.0.2	2026-04-03 18:51:03.004755	2026-04-06 19:09:01.83231	2026-04-03 18:51:47.555481
484	1	bb326266-cc34-4492-8d02-d120cc8a764b	MOBILE	EXPIRED	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-03 18:56:39.219754	2026-04-06 19:09:01.831826	2026-04-03 18:57:04.699947
504	3	051d7952-b0e3-4f04-8543-fdc40d613c78	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0	172.18.0.7	2026-04-11 09:38:12.337991	2026-04-14 10:47:38.495542	2026-04-11 09:40:36.686157
493	1	9ebcaf87-1b3e-4ed7-bae5-98c1b2de4dd2	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-09 18:57:38.318843	2026-04-10 08:26:25.712915	2026-04-10 08:25:56.227112
494	3	212bae3f-2c45-4757-97e5-722651e09b8b	MOBILE	KICKED_OUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-09 19:01:56.353211	2026-04-10 08:26:46.663912	2026-04-09 19:24:50.084761
498	3	e5768377-d4a0-49df-9478-670da4d45f5f	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-10 15:28:30.517327	2026-04-10 15:29:11.482984	2026-04-10 15:29:08.710366
491	1	cf90a329-513d-4641-8ce7-a7760d5fe55e	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-09 14:17:26.543578	\N	2026-04-09 16:44:44.63773
476	1	ba639b67-ead0-4818-85dc-a4878b85a241	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:45:08.99492	\N	2026-04-03 17:36:12.198071
474	3	f98b7fca-91e6-4163-ba67-4d5eb32d85ea	MOBILE	EXPIRED	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-03 14:10:39.342675	\N	2026-04-03 17:37:44.457962
496	3	d03c6fbd-550a-414e-a0db-a87eed91e78e	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-10 08:26:46.679649	2026-04-10 08:28:59.667454	2026-04-10 08:28:51.932398
478	3	649bc6a1-b4be-4595-8a2c-47b6fab7f2bb	MOBILE	KICKED_OUT	Mozilla/5.0 (Android 13; Mobile; rv:149.0) Gecko/149.0 Firefox/149.0	172.18.0.2	2026-04-03 17:40:07.666371	2026-04-03 18:09:29.47309	2026-04-03 17:40:22.819952
492	1	e9b0ec2d-bce2-478e-9c9d-a76b6635e5f8	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.4	2026-04-09 16:44:58.263427	2026-04-09 18:59:05.481402	2026-04-09 18:53:45.406241
499	1	a7455f75-c22d-425e-9dbb-7434b4531c9b	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-10 15:29:25.825874	2026-04-10 19:08:29.694671	2026-04-10 19:08:28.086643
481	3	b0e7909d-5edd-4b9d-94c4-bd4d05b2b749	MOBILE	KICKED_OUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-03 18:09:29.490245	2026-04-03 18:51:02.988724	2026-04-03 18:09:29.71981
495	1	0fceb5f8-f237-4898-a721-17664de32210	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-10 08:26:39.279104	2026-04-10 19:08:41.924206	2026-04-10 19:03:31.989624
490	1	da0f11de-de28-4edd-b73c-217ae863b005	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.3	2026-04-09 13:09:20.067079	\N	2026-04-09 14:17:15.082789
500	1	94287391-6408-4bee-a080-560a0e23d2a2	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.4	2026-04-10 19:08:48.493362	\N	2026-04-11 09:31:47.351792
479	1	532bc9bf-3add-476a-a00a-a80ea5e3fa29	MOBILE	KICKED_OUT	Mozilla/5.0 (Android 13; Mobile; rv:149.0) Gecko/149.0 Firefox/149.0	172.18.0.2	2026-04-03 17:41:55.126971	2026-04-03 18:55:31.468799	2026-04-03 17:42:07.05777
489	1	1b4a5fab-de0c-4863-9a4d-b9c779ae73ef	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.4	2026-04-09 12:16:46.570329	\N	2026-04-09 13:09:08.248566
483	1	b8ea584f-8613-4aa2-b25a-6e3b3fbfc1e3	MOBILE	KICKED_OUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-03 18:55:31.483493	2026-04-03 18:56:39.204098	2026-04-03 18:55:56.630759
501	1	90424fca-4ac5-4399-93de-9d853931f6ff	MOBILE	EXPIRED	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.4	2026-04-10 19:09:10.767999	2026-04-11 09:33:10.030963	2026-04-10 20:48:01.469504
480	1	e07a4f30-e8ae-4390-a369-09bb76f0d378	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.2	2026-04-03 17:52:52.726751	\N	2026-04-06 08:53:50.876515
502	1	7768a003-c86e-4b49-b46f-dea523f24b18	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.3	2026-04-11 09:32:52.275062	2026-04-11 09:34:39.205951	2026-04-11 09:34:05.82157
485	1	b0fcb918-3641-4669-99cc-1199518ac0ba	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.3	2026-04-06 09:16:03.87006	2026-04-09 09:29:21.365118	2026-04-09 08:42:40.324079
487	1	cef76b6c-9c1b-4e71-9795-da7badcfb262	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.2	2026-04-09 09:26:38.020545	2026-04-09 09:29:21.363669	2026-04-09 09:27:14.044383
475	1	1e4da845-0cb4-47a1-9d9f-3f78dc29a504	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36	172.18.0.4	2026-04-03 14:11:06.116763	2026-04-03 14:45:02.399443	2026-04-03 14:45:02.377759
497	1	c11b3493-a810-4471-a5c9-1966f69353a6	MOBILE	LOGOUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.2	2026-04-10 08:29:06.815945	2026-04-10 15:28:20.840128	2026-04-10 15:28:08.268587
503	1	a3088c4f-4693-4427-938c-825de13c86df	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.3	2026-04-11 09:34:39.225253	2026-04-11 09:42:12.120775	2026-04-11 09:37:25.004434
507	1	42d41db5-8adf-464f-b8b2-69b8c3767478	MOBILE	KICKED_OUT	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.6	2026-04-17 08:49:40.325676	2026-04-17 11:23:34.819336	2026-04-17 08:51:22.962151
505	1	37495282-06aa-4da3-b27f-243c23ee54b0	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.7	2026-04-11 09:42:12.140923	2026-04-14 10:46:35.064487	2026-04-14 09:33:12.435969
509	1	c1142148-52e1-4dbf-9513-bf9cf694ab9b	MOBILE	EXPIRED	Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36	172.18.0.6	2026-04-17 11:23:34.837045	2026-04-21 22:06:58.975454	2026-04-17 17:16:56.900026
511	1	7ce91889-bb33-42ef-a11d-6345500b2e83	DESKTOP	EXPIRED	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-17 19:08:41.951614	2026-04-21 22:06:58.974986	2026-04-18 15:49:38.678132
508	1	e981f1a1-84a9-4150-80a5-4213052a60d5	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-17 11:10:36.378834	2026-04-17 11:25:57.28241	2026-04-17 11:24:44.52034
513	1	16e3827f-889a-4b06-806f-694ef9b4b48c	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-21 22:06:49.465791	2026-04-22 16:09:48.194945	2026-04-22 16:09:44.475423
514	1	872fcc69-c963-4de8-980f-6dc39573ee12	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-23 12:49:39.676819	2026-04-23 12:50:24.008317	2026-04-23 12:50:08.56453
515	1	1abaa3ea-f562-42f9-95cf-033ab7e33d5a	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-23 12:50:34.654797	2026-04-23 12:50:46.637265	2026-04-23 12:50:34.997714
516	1	55390082-6599-4c81-adc6-634e028af169	DESKTOP	ACTIVE	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.4	2026-04-23 17:29:05.319723	\N	2026-04-23 17:29:25.198559
510	1	2477e2fe-3018-4799-8f2f-3587afb5eab1	DESKTOP	LOGOUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.6	2026-04-17 11:26:04.637862	2026-04-17 19:08:08.468431	2026-04-17 19:04:45.162758
517	1	6bc1ddb4-faaf-429c-b66f-11ef1aca5452	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.3	2026-04-23 17:48:43.516323	2026-04-23 18:27:25.561214	2026-04-23 17:57:26.410595
518	1	497b2091-0994-4bd9-af92-f947cd7c309c	DESKTOP	ACTIVE	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.3	2026-04-23 18:27:25.580601	\N	2026-04-23 18:27:26.112072
506	1	46d275bf-8cf0-44c8-88cf-0eb8574f880a	DESKTOP	KICKED_OUT	Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36	172.18.0.5	2026-04-14 10:46:35.079798	2026-04-17 11:10:36.35871	2026-04-17 09:42:48.191682
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, password, email, real_name, phone) FROM stdin;
3	kim	$2b$12$RCWfvk3RzHEpjPH62tH.luippmUkKW.yE/R2yk3XCE8iDPyoVWTHG	kim@kim.kim	\N	\N
4	park	$2b$12$q90Mzn0Z.l0EwAE.rO9KceU449Sur3lV73qJanrjult84cq3l1lwe	park@park.com	\N	\N
1	lee	$2b$12$.TT41ZXrO7CbNLsLi.7h7.HGDm476.kt8AeAY4QUDz/eEOs2FWsAO	lee@test.com	\N	\N
5	choi	$2b$12$fv0P.x65aV6QUXSObFeeU.C8KSkNZTBygj6scIpINa6zAnj.1PlkC	choi@choi.com	\N	\N
\.


--
-- Name: alert_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.alert_id_seq', 13, true);


--
-- Name: answer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.answer_id_seq', 1, false);


--
-- Name: board_config_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.board_config_id_seq', 4, true);


--
-- Name: comment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.comment_id_seq', 1, false);


--
-- Name: dayoff_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.dayoff_id_seq', 56, true);


--
-- Name: media_assets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.media_assets_id_seq', 21, true);


--
-- Name: menu_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.menu_id_seq', 37, true);


--
-- Name: page_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.page_id_seq', 3, true);


--
-- Name: post_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.post_id_seq', 8, true);


--
-- Name: post_read_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.post_read_id_seq', 11, true);


--
-- Name: push_subscription_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.push_subscription_id_seq', 11, true);


--
-- Name: question_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.question_id_seq', 6, true);


--
-- Name: question_image_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.question_image_id_seq', 1, false);


--
-- Name: service_app_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.service_app_id_seq', 2, true);


--
-- Name: service_instance_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.service_instance_id_seq', 1, true);


--
-- Name: tag_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tag_id_seq', 1, false);


--
-- Name: user_session_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.user_session_id_seq', 518, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 5, true);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: alert alert_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert
    ADD CONSTRAINT alert_pkey PRIMARY KEY (id);


--
-- Name: answer answer_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer
    ADD CONSTRAINT answer_pkey PRIMARY KEY (id);


--
-- Name: app_registry app_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_registry
    ADD CONSTRAINT app_registry_pkey PRIMARY KEY (app_id);


--
-- Name: board_config board_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_config
    ADD CONSTRAINT board_config_pkey PRIMARY KEY (id);


--
-- Name: comment comment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_pkey PRIMARY KEY (id);


--
-- Name: dayoff dayoff_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dayoff
    ADD CONSTRAINT dayoff_pkey PRIMARY KEY (id);


--
-- Name: media_assets media_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_pkey PRIMARY KEY (id);


--
-- Name: menu menu_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.menu
    ADD CONSTRAINT menu_pkey PRIMARY KEY (id);


--
-- Name: page page_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page
    ADD CONSTRAINT page_pkey PRIMARY KEY (id);


--
-- Name: post post_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post
    ADD CONSTRAINT post_pkey PRIMARY KEY (id);


--
-- Name: post_reaction post_reaction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_reaction
    ADD CONSTRAINT post_reaction_pkey PRIMARY KEY (user_id, post_id);


--
-- Name: post_read post_read_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_read
    ADD CONSTRAINT post_read_pkey PRIMARY KEY (id);


--
-- Name: post_tag post_tag_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_tag
    ADD CONSTRAINT post_tag_pkey PRIMARY KEY (post_id, tag_id);


--
-- Name: push_subscription push_subscription_endpoint_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscription
    ADD CONSTRAINT push_subscription_endpoint_key UNIQUE (endpoint);


--
-- Name: push_subscription push_subscription_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscription
    ADD CONSTRAINT push_subscription_pkey PRIMARY KEY (id);


--
-- Name: question_image question_image_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_image
    ADD CONSTRAINT question_image_pkey PRIMARY KEY (id);


--
-- Name: question question_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question
    ADD CONSTRAINT question_pkey PRIMARY KEY (id);


--
-- Name: question_reaction question_reaction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_reaction
    ADD CONSTRAINT question_reaction_pkey PRIMARY KEY (user_id, question_id);


--
-- Name: question_read_user question_read_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_read_user
    ADD CONSTRAINT question_read_user_pkey PRIMARY KEY (user_id, question_id);


--
-- Name: service_app service_app_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_app
    ADD CONSTRAINT service_app_pkey PRIMARY KEY (id);


--
-- Name: service_engine service_engine_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_engine
    ADD CONSTRAINT service_engine_pkey PRIMARY KEY (id);


--
-- Name: service_instance service_instance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_instance
    ADD CONSTRAINT service_instance_pkey PRIMARY KEY (id);


--
-- Name: service_registry service_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_registry
    ADD CONSTRAINT service_registry_pkey PRIMARY KEY (id);


--
-- Name: system_config system_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_config
    ADD CONSTRAINT system_config_pkey PRIMARY KEY (key);


--
-- Name: tag tag_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag
    ADD CONSTRAINT tag_name_key UNIQUE (name);


--
-- Name: tag tag_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag
    ADD CONSTRAINT tag_pkey PRIMARY KEY (id);


--
-- Name: post_read uq_user_post_read; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_read
    ADD CONSTRAINT uq_user_post_read UNIQUE (user_id, post_id);


--
-- Name: user_profiles user_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (user_id);


--
-- Name: user_session user_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_session
    ADD CONSTRAINT user_session_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: ix_app_registry_app_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_app_registry_app_id ON public.app_registry USING btree (app_id);


--
-- Name: ix_board_config_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_board_config_slug ON public.board_config USING btree (slug);


--
-- Name: ix_dayoff_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dayoff_group_id ON public.dayoff USING btree (group_id);


--
-- Name: ix_dayoff_user_date_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_dayoff_user_date_active ON public.dayoff USING btree (user_id, date) WHERE (is_deleted = false);


--
-- Name: ix_media_assets_app_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_assets_app_id ON public.media_assets USING btree (app_id);


--
-- Name: ix_media_assets_is_deleted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_assets_is_deleted ON public.media_assets USING btree (is_deleted);


--
-- Name: ix_media_assets_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_assets_target_id ON public.media_assets USING btree (target_id);


--
-- Name: ix_media_assets_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_assets_user_id ON public.media_assets USING btree (user_id);


--
-- Name: ix_page_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_page_slug ON public.page USING btree (slug);


--
-- Name: ix_system_config_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_config_key ON public.system_config USING btree (key);


--
-- Name: ix_user_session_device_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_session_device_category ON public.user_session USING btree (device_category);


--
-- Name: ix_user_session_last_activity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_session_last_activity ON public.user_session USING btree (last_activity);


--
-- Name: ix_user_session_login_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_session_login_at ON public.user_session USING btree (login_at);


--
-- Name: ix_user_session_session_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_session_session_key ON public.user_session USING btree (session_key);


--
-- Name: ix_user_session_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_session_status ON public.user_session USING btree (status);


--
-- Name: alert alert_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert
    ADD CONSTRAINT alert_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: answer answer_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer
    ADD CONSTRAINT answer_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question(id);


--
-- Name: answer answer_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer
    ADD CONSTRAINT answer_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: board_config board_config_service_instance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_config
    ADD CONSTRAINT board_config_service_instance_id_fkey FOREIGN KEY (service_instance_id) REFERENCES public.service_instance(id);


--
-- Name: comment comment_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.comment(id);


--
-- Name: comment comment_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.post(id);


--
-- Name: comment comment_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: dayoff dayoff_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dayoff
    ADD CONSTRAINT dayoff_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: media_assets media_assets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: menu menu_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.menu
    ADD CONSTRAINT menu_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.app_registry(app_id);


--
-- Name: menu menu_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.menu
    ADD CONSTRAINT menu_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.menu(id);


--
-- Name: post post_board_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post
    ADD CONSTRAINT post_board_id_fkey FOREIGN KEY (board_id) REFERENCES public.board_config(id);


--
-- Name: post_reaction post_reaction_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_reaction
    ADD CONSTRAINT post_reaction_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.post(id);


--
-- Name: post_reaction post_reaction_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_reaction
    ADD CONSTRAINT post_reaction_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: post_read post_read_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_read
    ADD CONSTRAINT post_read_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.post(id);


--
-- Name: post_read post_read_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_read
    ADD CONSTRAINT post_read_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: post_tag post_tag_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_tag
    ADD CONSTRAINT post_tag_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.post(id);


--
-- Name: post_tag post_tag_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_tag
    ADD CONSTRAINT post_tag_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tag(id);


--
-- Name: post post_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post
    ADD CONSTRAINT post_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: push_subscription push_subscription_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscription
    ADD CONSTRAINT push_subscription_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: question_image question_image_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_image
    ADD CONSTRAINT question_image_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question(id);


--
-- Name: question_reaction question_reaction_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_reaction
    ADD CONSTRAINT question_reaction_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question(id);


--
-- Name: question_reaction question_reaction_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_reaction
    ADD CONSTRAINT question_reaction_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: question_read_user question_read_user_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_read_user
    ADD CONSTRAINT question_read_user_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question(id);


--
-- Name: question_read_user question_read_user_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_read_user
    ADD CONSTRAINT question_read_user_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: question question_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question
    ADD CONSTRAINT question_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: service_app service_app_engine_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_app
    ADD CONSTRAINT service_app_engine_id_fkey FOREIGN KEY (engine_id) REFERENCES public.service_engine(id);


--
-- Name: service_engine service_engine_registry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_engine
    ADD CONSTRAINT service_engine_registry_id_fkey FOREIGN KEY (registry_id) REFERENCES public.service_registry(id);


--
-- Name: user_profiles user_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_session user_session_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_session
    ADD CONSTRAINT user_session_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict gaIXbyEruSpVJ7qbm4RUHIsNPnjissYbG8vISvKauuV1ghqhauUqaqHPop2XTk5

