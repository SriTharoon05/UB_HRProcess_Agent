# Fix the errors from the F&O build log

The reported errors have three causes: two syntax defects in the supplied portal service, renamed requirement fields still used by the existing service, and stale form bindings. The repository supplies the corrected portal class. The existing `UBHRApplicationService` and `UBJobRequirementForm` are not in this repository, so apply their field-reference fixes in Visual Studio as described below.

## 1. Replace the portal service source

Update the repository:

```powershell
git pull --ff-only origin main
```

In Visual Studio, open the actual AOT class **`UBHRPortalService`** in model **`UBHR_Nive`**. Replace its entire contents with [xpp/UBHRPortalService.xpp](xpp/UBHRPortalService.xpp), then save.

The locking statements now set the buffer's concurrency model and use only one selection hint:

```xpp
ttsBegin;

application.concurrencyModel(ConcurrencyModel::Pessimistic);
select firstOnly forUpdate application
    where application.ApplicationId == _request.parmApplicationId();

// Existing validation, updates and transaction completion follow.
```

The same pattern is applied to all six affected application, requirement, candidate and evaluation queries. `forUpdate` preserves update eligibility; the concurrency setting preserves pessimistic locking without combining mutually exclusive query hints. Both dictionary loops use **`enumElementIndex`** instead of the reserved keyword `index`.

The follow-on `}`, `)` and string-conversion errors near those loops may be parser cascades. Rebuild after replacing the complete class before treating those messages as independent defects.

## 2. Correct the existing application service's table accesses

Open the AOT class **`UBHRApplicationService`** in Visual Studio. Change accesses to fields on **`UBJobRequirementTable` buffers** using this mapping:

| Old requirement field | Existing field to use | Reported class line |
| --- | --- | ---: |
| `LocationName` | `JobLocation` | 36 |
| `NumberOfPositions` | `NumberOfOpenings` | 48 |
| `RequiredExperienceYears` | `MinimumExperienceYears` | 51 |
| `Qualification` | `RequiredQualifications` | 54 |

For example, if the table buffer is named `requirement`:

```xpp
requirement.JobLocation
requirement.NumberOfOpenings
requirement.MinimumExperienceYears
requirement.RequiredQualifications
```

Keep surrounding contract accessor names unless their actual contract definitions also changed. The compiler errors reported here concern the **table fields**. Apply the same table-field replacements in any `fieldNum`/`fieldStr` references to `UBJobRequirementTable` if present.

Limit these replacements to the requirement table. Your **`UBCandidateTable` still has `LocationName` and `Qualification`**, so a model-wide replacement would break valid candidate references.

## 3. Correct the requirement form bindings

Open **`UBJobRequirementForm`** in the form designer. Expand **Design → Controls → DetailsTabs**. Select these controls and change their **DataField** property, keeping **DataSource=`UBJobRequirementTable`**:

| Control under DetailsTabs | DataField to select |
| --- | --- |
| `GeneralTab → GeneralGroup → UBJobRequirementTable_LocationName` | `JobLocation` |
| `GeneralTabCopy1 → GeneralGroupCopy1 → UBJobRequirementTable_Qualification` | `RequiredQualifications` |
| `GeneralTabCopy1 → GeneralGroupCopy1 → UBJobRequirementTable_NumberOfPositions` | `NumberOfOpenings` |

The control's **Name** may keep its old value; binding uses **DataField**. Updating DataField is sufficient for the listed errors. Do not add the deleted/old field names back to the table.

## 4. Save and rebuild the model

1. Save the portal class, existing application service and form.
2. Build the affected project/model so it checks both service classes and the form. Removing a service from a service group does not fix an invalid class that remains in the model.
3. If the error list still points at old text, run Clean and then rebuild through the F&O Visual Studio tools.
4. Database synchronization is needed when table/index/EDT metadata changed. These class and form-binding corrections alone do not change the table schema.

The `C:\CustomXppMetadata...\XppSource\AxClass_*.xpp` paths in the error log identify generated build output. Make corrections in the AOT class editor and form designer; generated output will be recreated during the build.

The updated bundle has targeted source checks for the reported keyword/locking conflicts, plus its existing JSON/SQLite contract checks. The cloud workspace has no X++ compiler, so the final compilation result must be checked in your F&O Visual Studio environment.
