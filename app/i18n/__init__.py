from __future__ import annotations

from flask import Flask, g, request, url_for


DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "ko")
LOCALE_COOKIE_NAME = "mdms_locale"


MESSAGES = {
    "en": {
        "app.title": "MDMS Minimal E2E",
        "nav.dashboard": "Dashboard",
        "nav.raw_reads": "Raw Reads",
        "nav.raw_events": "Raw Events",
        "nav.exceptions": "Exceptions",
        "nav.master_data": "Master Data",
        "nav.language": "Language",
        "lang.en": "English",
        "lang.ko": "Korean",
        "flash.success": "Success",
        "flash.error": "Error",
        "dashboard.badge": "Minimal End-to-End",
        "dashboard.hero_title": "HES raw ingestion, mapping, canonicalization, and exceptions in one place",
        "dashboard.hero_body": (
            "This first scaffold is focused on the shortest believable operator flow: "
            "accept raw data, preserve it, map it to master data, and surface failures "
            "without hiding lineage."
        ),
        "dashboard.quick_start": "Quick Start",
        "dashboard.stage.waiting": "waiting",
        "dashboard.stage.processing": "processing",
        "dashboard.stage.completed": "completed",
        "dashboard.stage.failed": "failed",
        "dashboard.stage.raw_ingest": "Raw Ingest",
        "dashboard.stage.canonical": "Canonical",
        "dashboard.stage.errors": "Errors",
        "dashboard.service_points": "Service Points",
        "dashboard.devices": "Devices",
        "dashboard.raw_reads": "Raw Reads",
        "dashboard.exceptions": "Exceptions",
        "dashboard.recent_raw_reads": "Recent Raw Reads",
        "dashboard.recent_exceptions": "Recent Exceptions",
        "dashboard.view_all": "View all",
        "dashboard.view_queue": "View queue",
        "dashboard.no_raw_reads": "No raw reads loaded yet.",
        "dashboard.no_exceptions": "No exceptions recorded.",
        "page.raw_reads.title": "Raw Reads",
        "page.raw_reads.description": "Original meter reads are preserved before business-level processing.",
        "page.raw_events.title": "Raw Events",
        "page.raw_events.description": "HES events and alarms are stored separately so VEE can use them later.",
        "page.exceptions.title": "Exception Queue",
        "page.exceptions.description": "Mapping, validation, and duplicate issues are surfaced here for operator follow-up.",
        "page.master_data.title": "Master Data",
        "page.master_data.description": "Minimal device, service point, and measuring-component mappings used by the canonical flow.",
        "page.master_data.service_points": "Service Points",
        "page.master_data.devices": "Devices",
        "page.master_data.components": "Measuring Components",
        "page.master_data.create_service_point": "Create Service Point",
        "page.master_data.create_device": "Create Device",
        "page.master_data.create_component": "Create Measuring Component",
        "table.id": "ID",
        "table.source": "Source",
        "table.external_id": "External ID",
        "table.name": "Name",
        "table.service_type": "Service Type",
        "table.meter": "Meter",
        "table.channel": "Channel",
        "table.measured_at": "Measured At",
        "table.value": "Value",
        "table.status": "Status",
        "table.duplicate": "Duplicate",
        "table.event_time": "Event Time",
        "table.event_code": "Event Code",
        "table.severity": "Severity",
        "table.type": "Type",
        "table.code": "Code",
        "table.message": "Message",
        "table.component_id": "Component ID",
        "table.device_id": "Device ID",
        "table.serial_number": "Serial Number",
        "table.multiplier": "Multiplier",
        "table.external_channel": "External Channel",
        "table.service_point": "Service Point",
        "table.uom": "UOM",
        "table.actions": "Actions",
        "field.source_system": "Source System",
        "field.external_id": "External ID",
        "field.name": "Name",
        "field.service_type": "Service Type",
        "field.external_meter_id": "External Meter ID",
        "field.serial_number": "Serial Number",
        "field.service_point": "Service Point",
        "field.external_channel_id": "External Channel ID",
        "field.unit_of_measure": "Unit of Measure",
        "field.multiplier": "Multiplier",
        "field.device": "Device",
        "field.status": "Status",
        "button.create": "Create",
        "button.save": "Save",
        "common.none": "-",
        "common.yes": "yes",
        "common.no": "no",
        "common.status.active": "active",
        "common.status.installed": "installed",
        "common.status.open": "open",
        "common.status.inactive": "inactive",
        "common.service_type.electric": "electric",
        "common.service_type.gas": "gas",
        "common.service_type.water": "water",
        "exception_type.validation": "validation",
        "exception_type.duplicate": "duplicate",
        "exception_type.mapping": "mapping",
        "severity.high": "high",
        "severity.medium": "medium",
        "severity.low": "low",
        "canonical_status.mapped": "mapped",
        "canonical_status.duplicate": "duplicate",
        "canonical_status.exception": "exception",
        "page.raw_reads.empty": "No raw reads available.",
        "page.raw_events.empty": "No raw events available.",
        "page.exceptions.empty": "No exception records available.",
        "page.master_data.empty": "No master data loaded yet.",
        "api.errors.json_payload_required": "JSON payload is required.",
        "api.errors.ingest_request_failed": "The ingest request could not be processed.",
        "ingest.error.missing_required_fields": "Required raw read fields are missing.",
        "ingest.error.duplicate_raw_read": "Duplicate raw read detected for the same source, meter, channel, and timestamp.",
        "ingest.error.measuring_component_not_found": "No active measuring component matched the incoming raw read.",
        "ingest.error.invalid_event_payload": "Raw event is missing event_code or event_time.",
        "master_data.flash.service_point_created": "Service point created successfully.",
        "master_data.flash.service_point_updated": "Service point updated successfully.",
        "master_data.flash.device_created": "Device created successfully.",
        "master_data.flash.device_updated": "Device updated successfully.",
        "master_data.flash.component_created": "Measuring component created successfully.",
        "master_data.flash.component_updated": "Measuring component updated successfully.",
        "master_data.error.missing_source_system": "Source system is required.",
        "master_data.error.missing_external_id": "External identifier is required.",
        "master_data.error.missing_service_type": "Service type is required.",
        "master_data.error.missing_status": "Status is required.",
        "master_data.error.invalid_status": "Status must be active or inactive.",
        "master_data.error.duplicate_service_point_external_id": "A service point with the same external identifier already exists.",
        "master_data.error.missing_external_meter_id": "External meter identifier is required.",
        "master_data.error.missing_service_point_id": "Service point selection is required.",
        "master_data.error.service_point_not_found": "The selected service point does not exist.",
        "master_data.error.duplicate_device_external_meter_id": "A device with the same external meter identifier already exists.",
        "master_data.error.device_service_point_component_mismatch": "The selected service point conflicts with existing measuring component mappings.",
        "master_data.error.missing_external_channel_id": "External channel identifier is required.",
        "master_data.error.missing_unit_of_measure": "Unit of measure is required.",
        "master_data.error.missing_multiplier": "Multiplier is required.",
        "master_data.error.invalid_multiplier": "Multiplier must be greater than zero.",
        "master_data.error.missing_device_id": "Device selection is required.",
        "master_data.error.device_not_found": "The selected device does not exist.",
        "master_data.error.component_not_found": "The selected measuring component does not exist.",
        "master_data.error.component_service_point_device_mismatch": "The selected service point does not match the device mapping.",
        "master_data.error.duplicate_component_channel": "A measuring component with the same source, device, and external channel already exists.",
    },
    "ko": {
        "app.title": "MDMS 최소 E2E",
        "nav.dashboard": "대시보드",
        "nav.raw_reads": "원시 검침",
        "nav.raw_events": "원시 이벤트",
        "nav.exceptions": "오류 큐",
        "nav.master_data": "마스터 데이터",
        "nav.language": "언어",
        "lang.en": "영문",
        "lang.ko": "한글",
        "flash.success": "성공",
        "flash.error": "오류",
        "dashboard.badge": "최소 End-to-End",
        "dashboard.hero_title": "HES 원시 수집, 매핑, 표준화, 예외 처리를 한 곳에서 확인합니다",
        "dashboard.hero_body": (
            "현재 스캐폴드는 가장 짧고 믿을 수 있는 운영 흐름에 집중합니다. "
            "원시 데이터를 수용하고 보존한 뒤, 마스터 데이터에 매핑하고, "
            "lineage를 잃지 않으면서 실패를 드러냅니다."
        ),
        "dashboard.quick_start": "빠른 시작",
        "dashboard.stage.waiting": "대기",
        "dashboard.stage.processing": "처리 중",
        "dashboard.stage.completed": "완료",
        "dashboard.stage.failed": "실패",
        "dashboard.stage.raw_ingest": "원시 적재",
        "dashboard.stage.canonical": "표준화",
        "dashboard.stage.errors": "오류",
        "dashboard.service_points": "서비스 포인트",
        "dashboard.devices": "계량기",
        "dashboard.raw_reads": "원시 검침",
        "dashboard.exceptions": "오류",
        "dashboard.recent_raw_reads": "최근 원시 검침",
        "dashboard.recent_exceptions": "최근 오류",
        "dashboard.view_all": "전체 보기",
        "dashboard.view_queue": "큐 보기",
        "dashboard.no_raw_reads": "적재된 원시 검침이 없습니다.",
        "dashboard.no_exceptions": "기록된 오류가 없습니다.",
        "page.raw_reads.title": "원시 검침",
        "page.raw_reads.description": "원시 검침 데이터는 업무 처리 전에 먼저 보존됩니다.",
        "page.raw_events.title": "원시 이벤트",
        "page.raw_events.description": "HES 이벤트와 알람은 이후 VEE 활용을 위해 별도로 보관됩니다.",
        "page.exceptions.title": "오류 큐",
        "page.exceptions.description": "매핑, 검증, 중복 관련 문제를 운영자가 후속 처리할 수 있도록 보여줍니다.",
        "page.master_data.title": "마스터 데이터",
        "page.master_data.description": "표준화 흐름에서 사용하는 최소 장치, 서비스 포인트, 채널 매핑입니다.",
        "page.master_data.service_points": "서비스 포인트",
        "page.master_data.devices": "장치",
        "page.master_data.components": "측정 컴포넌트",
        "page.master_data.create_service_point": "서비스 포인트 등록",
        "page.master_data.create_device": "장치 등록",
        "page.master_data.create_component": "측정 컴포넌트 등록",
        "table.id": "ID",
        "table.source": "출처",
        "table.external_id": "외부 ID",
        "table.name": "이름",
        "table.service_type": "서비스 유형",
        "table.meter": "계량기",
        "table.channel": "채널",
        "table.measured_at": "검침 시각",
        "table.value": "값",
        "table.status": "상태",
        "table.duplicate": "중복",
        "table.event_time": "이벤트 시각",
        "table.event_code": "이벤트 코드",
        "table.severity": "심각도",
        "table.type": "유형",
        "table.code": "코드",
        "table.message": "메시지",
        "table.component_id": "컴포넌트 ID",
        "table.device_id": "장치 ID",
        "table.serial_number": "시리얼 번호",
        "table.multiplier": "배율",
        "table.external_channel": "외부 채널",
        "table.service_point": "서비스 포인트",
        "table.uom": "단위",
        "table.actions": "동작",
        "field.source_system": "출처 시스템",
        "field.external_id": "외부 ID",
        "field.name": "이름",
        "field.service_type": "서비스 유형",
        "field.external_meter_id": "외부 계량기 ID",
        "field.serial_number": "시리얼 번호",
        "field.service_point": "서비스 포인트",
        "field.external_channel_id": "외부 채널 ID",
        "field.unit_of_measure": "단위",
        "field.multiplier": "배율",
        "field.device": "장치",
        "field.status": "상태",
        "button.create": "등록",
        "button.save": "저장",
        "common.none": "-",
        "common.yes": "예",
        "common.no": "아니오",
        "common.status.active": "활성",
        "common.status.installed": "설치됨",
        "common.status.open": "대기",
        "common.status.inactive": "비활성",
        "common.service_type.electric": "전기",
        "common.service_type.gas": "가스",
        "common.service_type.water": "수도",
        "exception_type.validation": "검증",
        "exception_type.duplicate": "중복",
        "exception_type.mapping": "매핑",
        "severity.high": "높음",
        "severity.medium": "보통",
        "severity.low": "낮음",
        "canonical_status.mapped": "매핑 완료",
        "canonical_status.duplicate": "중복",
        "canonical_status.exception": "예외",
        "page.raw_reads.empty": "원시 검침 데이터가 없습니다.",
        "page.raw_events.empty": "원시 이벤트가 없습니다.",
        "page.exceptions.empty": "오류 기록이 없습니다.",
        "page.master_data.empty": "적재된 마스터 데이터가 없습니다.",
        "api.errors.json_payload_required": "JSON 페이로드가 필요합니다.",
        "api.errors.ingest_request_failed": "적재 요청을 처리할 수 없습니다.",
        "ingest.error.missing_required_fields": "필수 원시 검침 항목이 누락되었습니다.",
        "ingest.error.duplicate_raw_read": "같은 출처, 계량기, 채널, 시각 조합의 중복 원시 검침이 감지되었습니다.",
        "ingest.error.measuring_component_not_found": "수신한 원시 검침과 일치하는 활성 측정 컴포넌트를 찾지 못했습니다.",
        "ingest.error.invalid_event_payload": "원시 이벤트에 event_code 또는 event_time이 없습니다.",
        "master_data.flash.service_point_created": "서비스 포인트가 등록되었습니다.",
        "master_data.flash.service_point_updated": "서비스 포인트가 수정되었습니다.",
        "master_data.flash.device_created": "장치가 등록되었습니다.",
        "master_data.flash.device_updated": "장치가 수정되었습니다.",
        "master_data.flash.component_created": "측정 컴포넌트가 등록되었습니다.",
        "master_data.flash.component_updated": "측정 컴포넌트가 수정되었습니다.",
        "master_data.error.missing_source_system": "출처 시스템은 필수입니다.",
        "master_data.error.missing_external_id": "외부 ID는 필수입니다.",
        "master_data.error.missing_service_type": "서비스 유형은 필수입니다.",
        "master_data.error.missing_status": "상태는 필수입니다.",
        "master_data.error.invalid_status": "상태는 active 또는 inactive 여야 합니다.",
        "master_data.error.duplicate_service_point_external_id": "같은 외부 ID를 가진 서비스 포인트가 이미 존재합니다.",
        "master_data.error.missing_external_meter_id": "외부 계량기 ID는 필수입니다.",
        "master_data.error.missing_service_point_id": "서비스 포인트 선택은 필수입니다.",
        "master_data.error.service_point_not_found": "선택한 서비스 포인트가 존재하지 않습니다.",
        "master_data.error.duplicate_device_external_meter_id": "같은 외부 계량기 ID를 가진 장치가 이미 존재합니다.",
        "master_data.error.device_service_point_component_mismatch": "선택한 서비스 포인트가 기존 측정 컴포넌트 매핑과 충돌합니다.",
        "master_data.error.missing_external_channel_id": "외부 채널 ID는 필수입니다.",
        "master_data.error.missing_unit_of_measure": "단위는 필수입니다.",
        "master_data.error.missing_multiplier": "배율은 필수입니다.",
        "master_data.error.invalid_multiplier": "배율은 0보다 커야 합니다.",
        "master_data.error.missing_device_id": "장치 선택은 필수입니다.",
        "master_data.error.device_not_found": "선택한 장치가 존재하지 않습니다.",
        "master_data.error.component_not_found": "선택한 측정 컴포넌트가 존재하지 않습니다.",
        "master_data.error.component_service_point_device_mismatch": "선택한 서비스 포인트가 장치 매핑과 일치하지 않습니다.",
        "master_data.error.duplicate_component_channel": "같은 출처, 장치, 외부 채널 조합의 측정 컴포넌트가 이미 존재합니다.",
    },
}


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None

    compact = value.strip().replace("_", "-")
    if not compact:
        return None

    primary = compact.split("-", maxsplit=1)[0].lower()
    if primary in SUPPORTED_LOCALES:
        return primary

    return None


def detect_locale() -> str:
    explicit = normalize_locale(request.args.get("lang"))
    if explicit:
        return explicit

    cookie_locale = normalize_locale(request.cookies.get(LOCALE_COOKIE_NAME))
    if cookie_locale:
        return cookie_locale

    for accepted, _quality in request.accept_languages:
        accepted_locale = normalize_locale(accepted)
        if accepted_locale:
            return accepted_locale

    return DEFAULT_LOCALE


def get_locale() -> str:
    return getattr(g, "locale", DEFAULT_LOCALE)


def translate(key: str, locale: str | None = None, **kwargs) -> str:
    target_locale = normalize_locale(locale) or get_locale()
    template = MESSAGES.get(target_locale, {}).get(key)
    if template is None:
        template = MESSAGES[DEFAULT_LOCALE].get(key, key)
    return template.format(**kwargs)


def translate_or(key: str, fallback: str, locale: str | None = None, **kwargs) -> str:
    localized = translate(key, locale=locale, **kwargs)
    if localized == key:
        return fallback
    return localized


def translate_ingest_error(code: str, fallback_message: str | None = None) -> str:
    key = f"ingest.error.{code}"
    return translate_or(key, fallback_message or code)


def translate_master_data_error(code: str, fallback_message: str | None = None) -> str:
    key = f"master_data.error.{code}"
    return translate_or(key, fallback_message or code)


def localized_url(target_locale: str) -> str:
    normalized_locale = normalize_locale(target_locale) or DEFAULT_LOCALE
    if request.endpoint is None:
        return request.path

    values = dict(request.view_args or {})
    values.update(request.args.to_dict(flat=True))
    values["lang"] = normalized_locale
    return url_for(request.endpoint, **values)


def register_i18n(app: Flask) -> None:
    @app.before_request
    def assign_locale() -> None:
        g.locale = detect_locale()

    @app.after_request
    def persist_locale(response):
        if "lang" in request.args:
            response.set_cookie(
                LOCALE_COOKIE_NAME,
                normalize_locale(request.args.get("lang")) or DEFAULT_LOCALE,
                samesite="Lax",
            )
        return response

    @app.context_processor
    def inject_i18n_helpers() -> dict[str, object]:
        return {
            "current_locale": get_locale(),
            "supported_locales": SUPPORTED_LOCALES,
            "localized_url": localized_url,
            "t": translate,
            "t_or": translate_or,
            "t_ingest_error": translate_ingest_error,
            "t_master_data_error": translate_master_data_error,
        }
