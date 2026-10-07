using System.Diagnostics;
using System.IO;

namespace WatchNetUi;

/// <summary>barsSaver CSV health — same stale-M1-behind-M10 idea as the Lua patch.</summary>
public static class BarsHealth
{
    /// <summary>Match barsSaver_params.ini STALE_M1_BEHIND_M10_SEC.</summary>
    public const int StaleM1BehindM10Sec = 120;

    /// <summary>M1 write older than this → ticker looks frozen (market open).</summary>
    public const int M1StaleSec = 180;

    /// <summary>Soft warn before hard stale.</summary>
    public const int M1WarnSec = 90;

    public sealed record InstrumentBars(
        DateTime? M1,
        DateTime? M10,
        string Status,
        string AgeText,
        bool IsStale,
        bool IsBehindM10);

    public sealed record Snapshot(
        bool QuikRunning,
        bool BarsDirOk,
        int Instruments,
        int FreshM1,
        int WarnM1,
        int StaleM1,
        int BehindM10,
        int MissingM1,
        DateTime? NewestM1,
        DateTime? OldestM1,
        string Summary);

    public static string BarsM10Path(string sec, string classCode, string? barsDir = null)
        => Path.Combine(barsDir ?? Paths.BarsDir, $"{sec}_{classCode}_M10_.csv");

    public static InstrumentBars ForInstrument(string sec, string classCode, DateTime now, string? barsDir = null)
    {
        var m1 = InstrumentScanner.FileWriteUtc(InstrumentScanner.BarsM1Path(sec, classCode, barsDir));
        var m10 = InstrumentScanner.FileWriteUtc(BarsM10Path(sec, classCode, barsDir));
        if (m1 == null)
        {
            return new InstrumentBars(null, m10, "нет M1", "—", true, false);
        }

        var age = now - m1.Value;
        var ageText = FormatAge(age);
        var behind = m10 != null && (m10.Value - m1.Value).TotalSeconds > StaleM1BehindM10Sec;
        if (behind)
        {
            var lag = FormatAge(m10!.Value - m1.Value);
            return new InstrumentBars(m1, m10, $"M1≪M10 {lag}", ageText, true, true);
        }

        if (age.TotalSeconds >= M1StaleSec)
            return new InstrumentBars(m1, m10, "stale M1", ageText, true, false);
        if (age.TotalSeconds >= M1WarnSec)
            return new InstrumentBars(m1, m10, "тихо", ageText, false, false);
        return new InstrumentBars(m1, m10, "ok", ageText, false, false);
    }

    public static Snapshot Build(IEnumerable<(string Sec, string ClassCode)> instruments, DateTime now)
    {
        var quik = Process.GetProcessesByName("info").Length > 0;
        var dirOk = Directory.Exists(Paths.BarsDir);
        var list = instruments.ToList();
        var fresh = 0;
        var warn = 0;
        var stale = 0;
        var behind = 0;
        var missing = 0;
        DateTime? newest = null;
        DateTime? oldest = null;

        foreach (var (sec, cls) in list)
        {
            var b = ForInstrument(sec, cls, now);
            if (b.M1 == null)
            {
                missing++;
                continue;
            }

            if (newest == null || b.M1 > newest) newest = b.M1;
            if (oldest == null || b.M1 < oldest) oldest = b.M1;

            if (b.IsBehindM10) behind++;
            if (b.IsStale && !b.IsBehindM10) stale++;
            else if (b.Status == "тихо") warn++;
            else if (b.Status == "ok") fresh++;
        }

        string summary;
        if (!dirOk)
            summary = $"barsSaver: нет папки {Paths.BarsDir}";
        else if (!quik)
            summary = $"barsSaver: QUIK (info.exe) не найден · M1 ok {fresh}/{list.Count} · stale {stale} · M1≪M10 {behind}";
        else if (behind > 0 || stale > 0)
            summary =
                $"barsSaver: QUIK ok · M1 свежих {fresh}/{list.Count} · тихо {warn} · stale {stale} · M1≪M10 {behind}"
                + (newest != null ? $" · newest {FormatAge(now - newest.Value)}" : "");
        else
            summary =
                $"barsSaver: QUIK ok · M1 свежих {fresh}/{list.Count}"
                + (warn > 0 ? $" · тихо {warn}" : "")
                + (newest != null ? $" · newest {FormatAge(now - newest.Value)}" : "")
                + (missing > 0 ? $" · нет M1 {missing}" : "");

        return new Snapshot(
            quik, dirOk, list.Count, fresh, warn, stale, behind, missing, newest, oldest, summary);
    }

    public static string FormatAge(TimeSpan t)
    {
        if (t.TotalSeconds < 0) t = -t;
        if (t.TotalHours >= 1) return $"{(int)t.TotalHours}ч {t.Minutes:D2}м";
        if (t.TotalMinutes >= 1) return $"{(int)t.TotalMinutes}м {t.Seconds:D2}с";
        return $"{(int)t.TotalSeconds}с";
    }
}
