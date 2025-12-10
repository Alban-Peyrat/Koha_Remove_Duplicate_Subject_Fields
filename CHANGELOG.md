# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

* Changed behaviour when encountering a field sharing the same ID as a stored field :
  * If stored field has no PPN but the new field has PPNs, keeps the new field
  * If both stored field & new field has PPN, keep the field the closest of having the same number of `$9` & `PPN`. If both have the same number, keep the stored field
  * If neither has PPN, keep the stored field
  * In all cases where the stored fielf is kept, unless the new field worse PPN situation, checks if alphabet / script for latin, with the following priority :
      1. `$7` has value `ba0yba0y`
      1. `$7` has value `ba`
      1. `$7` has another value or no value
  * ... if the new field has an higher priority than the stored one, keeps the new field

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
