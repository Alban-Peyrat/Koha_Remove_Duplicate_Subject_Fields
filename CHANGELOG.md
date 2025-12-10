# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

* `prep_list.py` now properly deals with Koha's CSV BOM
* `prep_list.py` no longer outputs headers as the main script does not expect headers

## [1.0.2] - 2025-10-01

### Fixed

* `prep_list.py` now works with CSV exports from Koha 24.11.XX, which now uses BOM

## [1.0.1] - 2025-03-10

### Changed

* Fields constructed with multiple terms are now identified as the concatenation of their IDs
  * Ex : RAMEAU terms with geographical subdivision
  * Ex : `$9123$aJardin$9987$xChine` is now identified as `123-987` (used to be only `123`)

## [1.0.0] - 2025-02-18

Original release
