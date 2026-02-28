"use client"

import React, { useState, useRef } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts'
import { Activity, LayoutDashboard, FileText, ArrowUpRight, DollarSign, Wallet, MoreHorizontal, Download, UploadCloud, FileSpreadsheet, Plus, Minus, CheckCircle2 } from 'lucide-react'

export default function DashboardPage() {
  const [file, setFile] = useState<File | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [dashboardData, setDashboardData] = useState<any>(null)
  const [exporting, setExporting] = useState(false)
  const [viewMode, setViewMode] = useState<'management' | 'schedule3'>('schedule3')
  const [expandedOpex, setExpandedOpex] = useState(false)

  // CA Sandbox
  const [assumptions, setAssumptions] = useState({
    revenue_growth: '',
    tax_rate: '15.0',
    new_capex: ''
  })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dashboardRef = useRef<HTMLDivElement>(null)

  const handleExportPDF = async () => {
    if (!dashboardRef.current) return
    setExporting(true)

    try {
      const html2canvas = (await import('html2canvas')).default
      const jsPDFModule = await import('jspdf')
      const jsPDF = (jsPDFModule as any).jsPDF || (jsPDFModule as any).default

      // A4 Landscape
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
      const pageWidth = 297
      const pageHeight = 210
      const margin = 12
      const contentWidth = pageWidth - 2 * margin
      const contentHeight = pageHeight - 2 * margin

      // ═══ COVER PAGE ═══
      pdf.setFillColor(15, 23, 42)
      pdf.rect(0, 0, pageWidth, pageHeight, 'F')

      pdf.setFillColor(79, 70, 229)
      pdf.rect(margin, 62, 50, 2.5, 'F')

      pdf.setTextColor(255, 255, 255)
      pdf.setFontSize(32)
      pdf.setFont('helvetica', 'bold')
      pdf.text('FinCast CMA Report', margin, 80)

      pdf.setFontSize(14)
      pdf.setFont('helvetica', 'normal')
      pdf.setTextColor(148, 163, 184)
      pdf.text(file?.name || 'Financial Analysis', margin, 95)

      pdf.setFontSize(11)
      const dateStr = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
      pdf.text(`Generated: ${dateStr}`, margin, 108)

      pdf.setFontSize(10)
      pdf.setTextColor(100, 116, 139)
      pdf.text(
        viewMode === 'schedule3' ? 'Schedule III \u2014 Indirect Method (Audit View)' : 'Direct Method \u2014 Management View',
        margin, 120
      )

      if (kpis) {
        pdf.setFontSize(10)
        pdf.setTextColor(148, 163, 184)
        pdf.text(`Projected 12-Month Revenue: ${formatINR(kpis.projected_12m)}`, margin, 145)
        pdf.text(`EBITDA: ${formatINR(kpis.ebitda)}  |  Net Margin: ${kpis.net_margin}%  |  DSO: ${kpis.calculated_dso} days`, margin, 155)
        if (tax_metadata) {
          pdf.text(`Estimated Annual Tax Liability: ${formatINR(tax_metadata.estimated_annual_tax)}`, margin, 165)
        }
      }

      pdf.setTextColor(71, 85, 105)
      pdf.setFontSize(9)
      pdf.text('Powered by FinCast Intelligence Engine', margin, pageHeight - 15)
      pdf.text('Confidential', pageWidth - margin, pageHeight - 15, { align: 'right' })

      // ═══ CONTENT PAGES ═══
      const exportHideEls = dashboardRef.current.querySelectorAll('[data-export-hide]')
      const savedDisplays: string[] = []
      exportHideEls.forEach((el, i) => {
        const htmlEl = el as HTMLElement
        savedDisplays[i] = htmlEl.style.display
        htmlEl.style.display = 'none'
      })

      const canvas = await html2canvas(dashboardRef.current, {
        scale: 1.5,
        useCORS: true,
        backgroundColor: '#ffffff',
        logging: false,
        windowWidth: 1400,
        removeContainer: true,
        onclone: (clonedDoc: Document) => {
          // Strip backdrop-filter — html2canvas crashes on this property
          clonedDoc.querySelectorAll('*').forEach((el) => {
            const htmlEl = el as HTMLElement
            if (htmlEl.style) {
              htmlEl.style.backdropFilter = 'none'
              htmlEl.style.setProperty('-webkit-backdrop-filter', 'none')
            }
          })
          // Also strip it from computed style overrides via class
          const style = clonedDoc.createElement('style')
          style.textContent = '* { backdrop-filter: none !important; -webkit-backdrop-filter: none !important; }'
          clonedDoc.head.appendChild(style)
        },
      })

      exportHideEls.forEach((el, i) => {
        (el as HTMLElement).style.display = savedDisplays[i]
      })

      const imgData = canvas.toDataURL('image/jpeg', 0.92)
      const imgWidth = contentWidth
      const imgHeight = (canvas.height * contentWidth) / canvas.width

      let heightLeft = imgHeight
      let position = 0

      while (heightLeft > 0) {
        pdf.addPage()
        pdf.addImage(imgData, 'JPEG', margin, margin - position, imgWidth, imgHeight)

        const pageNum = pdf.getNumberOfPages() - 1
        pdf.setFontSize(7)
        pdf.setTextColor(180, 180, 180)
        pdf.text(`FinCast CMA Report \u2014 ${file?.name || ''}`, margin, pageHeight - 4)
        pdf.text(`Page ${pageNum}`, pageWidth - margin, pageHeight - 4, { align: 'right' })

        heightLeft -= contentHeight
        position += contentHeight
      }

      const safeName = (file?.name?.replace(/\.[^/.]+$/, '') || 'Report').replace(/[^a-zA-Z0-9_\-]/g, '_')
      pdf.save(`FinCast_${safeName}_${new Date().toISOString().split('T')[0]}.pdf`)

    } catch (error) {
      console.error('PDF export failed:', error)
      alert('PDF export failed. Please try again.')
    } finally {
      setExporting(false)
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selected = e.target.files[0]
      setFile(selected)
      await analyzeDocument(selected)
    }
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const selected = e.dataTransfer.files[0]
      setFile(selected)
      await analyzeDocument(selected)
    }
  }

  const analyzeDocument = async (uploadFile: File, currentAssumptions = assumptions) => {
    setAnalyzing(true)

    const formData = new FormData()
    formData.append("file", uploadFile)
    formData.append("assumptions", JSON.stringify(currentAssumptions))

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/analyze`, {
        method: "POST",
        body: formData,
      })

      const resData = await res.json().catch(() => null)

      if (!res.ok) {
        throw new Error(resData?.detail || "Failed to analyze data")
      }

      setDashboardData(resData)
    } catch (error: any) {
      console.error(error)
      alert(error.message || "Error analyzing file. Ensure backend is running and API key is set.")
    } finally {
      setAnalyzing(false)
    }
  }

  // Formatting for Rs.
  const formatINR = (val: number) => {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val || 0)
  }

  // View: Upload Interface
  if (!dashboardData && !analyzing) {
    return (
      <div className="min-h-screen animate-in fade-in duration-[1500ms] bg-[#F9FAFB] bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-50/20 via-slate-50/50 to-white flex flex-col items-center justify-center p-6 text-slate-800 font-sans selection:bg-indigo-100">
        <div className="max-w-2xl w-full text-center space-y-10 animate-in slide-in-from-bottom-8 duration-1000 zoom-in-95">
          <div>
            <div className="inline-flex items-center justify-center p-3 bg-white/80 backdrop-blur-3xl shadow-sm rounded-2xl mb-6 border border-slate-100">
              <Activity className="w-8 h-8 text-indigo-600" />
            </div>
            <h1 className="text-5xl font-extrabold tracking-tight text-slate-800">
              FinCast Intelligence
            </h1>
            <p className="text-slate-500/90 mt-5 text-xl print:text-sm max-w-xl mx-auto leading-relaxed">
              Upload any chaotic SME ledger. Our Agentic AI normalizes the data and mathematically derives your <span className="font-semibold text-slate-800">Schedule III compliant</span> CMA projection.
            </p>
          </div>

          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="group relative flex flex-col items-center justify-center p-20 rounded-[2rem] border-2 border-dashed border-slate-200 bg-white/80 backdrop-blur-3xl hover:bg-slate-50 hover:border-indigo-400 transition-all cursor-pointer shadow-sm hover:shadow-md"
          >
            <div className="absolute inset-0 bg-indigo-50/0 group-hover:bg-indigo-50/50 rounded-[2rem] transition-colors"></div>
            <UploadCloud className="w-16 h-16 text-indigo-500 mb-6 group-hover:-translate-y-2 transition-transform duration-500 ease-out" />
            <h3 className="text-2xl font-bold mb-3 text-slate-800">Drag & Drop Financials</h3>
            <p className="text-slate-500/90 font-medium tracking-wide">Supports ugly Tally .xlsx, .xls, and .csv exports</p>
            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
              onChange={handleFileChange}
            />
          </div>
        </div>
      </div>
    )
  }

  // View: Skeleton Loading 
  if (analyzing) {
    return (
      <div className="min-h-screen animate-in fade-in duration-[1500ms] bg-[#F9FAFB] bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-50/20 via-slate-50/50 to-white flex flex-col items-center justify-center p-6 text-slate-800 font-sans">
        <div className="bg-white/80 backdrop-blur-3xl p-12 rounded-3xl shadow-xl border border-slate-100 flex flex-col items-center max-w-md w-full">
          <Activity className="w-12 h-12 text-indigo-600 animate-spin mb-6" />
          <h2 className="text-2xl font-bold mb-6 text-slate-800">Normalizing Chaos...</h2>
          <div className="space-y-4 text-slate-500/90 font-medium text-sm w-full">
            <p className="animate-pulse flex items-center gap-3"><span className="w-2 h-2 rounded-full bg-indigo-500" /> Scanning strict CA ledger logic...</p>
            <p className="animate-pulse delay-75 flex items-center gap-3"><span className="w-2 h-2 rounded-full bg-indigo-500" /> Extracting granular line items...</p>
            <p className="animate-pulse delay-150 flex items-center gap-3"><span className="w-2 h-2 rounded-full bg-indigo-500" /> Executing Adaptive Holt-Winters projection...</p>
            <p className="animate-pulse delay-300 flex items-center gap-3"><span className="w-2 h-2 rounded-full bg-indigo-500" /> Formatting Schedule III Indirect Matrix...</p>
          </div>
        </div>
      </div>
    )
  }

  // View: The Dashboard
  const { kpis, charts, three_way_model, tax_metadata } = dashboardData

  return (
    <div className="min-h-screen animate-in fade-in duration-[1500ms] bg-[#F9FAFB] bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-50/20 via-slate-50/50 to-white text-slate-800 p-6 md:p-12 font-sans print:bg-white print:p-0">

      {/* Header */}
      <header className="flex flex-col md:flex-row items-start md:items-center justify-between mb-10 gap-6 print:mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-800">FinCast CMA Report</h1>
          <p className="text-slate-500/90 mt-2 flex items-center gap-2 font-medium">
            <FileSpreadsheet size={16} className="text-indigo-500" />
            {file?.name} • Algorithmically Forecasted
          </p>
        </div>
        <div className="flex items-center gap-4 print:hidden mobile-stack flex-wrap" data-export-hide>
          {/* Toggle Switch */}
          <div className="flex bg-white/80 backdrop-blur-3xl p-1 rounded-xl shadow-sm border border-slate-200">
            <button
              onClick={() => setViewMode('management')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${viewMode === 'management' ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-slate-500/90 hover:text-slate-700'}`}
            >
              <LayoutDashboard size={16} /> Management View
            </button>
            <button
              onClick={() => setViewMode('schedule3')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${viewMode === 'schedule3' ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-slate-500/90 hover:text-slate-700'}`}
            >
              <FileText size={16} /> Schedule III (Audit)
            </button>
          </div>

          <button
            disabled={exporting}
            onClick={handleExportPDF}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 transition-all shadow-md hover:shadow-lg disabled:opacity-50"
          >
            {exporting ? <Activity className="animate-spin w-4 h-4" /> : <Download size={16} />}
            {exporting ? "Generating PDF..." : "Export PDF"}
          </button>
        </div>
      </header>

      <div ref={dashboardRef} className="pb-20 space-y-12 animate-in slide-in-from-bottom-12 duration-1000">

        {/* Premium Advanced KPIs */}
        <div className="kpi-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 print:grid-cols-4 print:gap-4">
          {[
            { title: 'Projected Outlook (12m)', value: formatINR(kpis.projected_12m), change: 'Holt-Winters Baseline Baseline', icon: <Activity size={20} className="text-emerald-600" />, detail: "Exponential smoothing projection based on extracted revenue trajectory.", bg: "bg-emerald-50" },
            { title: 'EBITDA (Latest Period)', value: formatINR(kpis.ebitda), change: 'Core Operating Profit', icon: <DollarSign size={20} className="text-indigo-600" />, detail: "Calculated dynamically: Revenue - COGS - OpEx - Payroll.", bg: "bg-indigo-50" },
            { title: 'Gross vs Net Margin', value: `${kpis.net_margin}%`, change: `Gross: ${kpis.gross_margin}%`, icon: <ArrowUpRight size={20} className="text-sky-600" />, detail: "Profitability matrix subtracting Debt Service and Capex outflows.", bg: "bg-sky-50" },
            { title: 'Liquidity Ratios (DSO / DPO)', value: `${kpis.calculated_dso} / ${kpis.calculated_dpo}`, change: 'Days to Pay vs Get Paid', icon: <Wallet size={20} className="text-amber-600" />, detail: "Advanced Countback exhaustion of actual Receivable/Payable outstanding.", bg: "bg-amber-50" },
          ].map((kpi, i) => (
            <div key={i} className={`group p-5 md:p-8 animate-in slide-in-from-bottom-8 fade-in duration-700 delay-[${i * 150}ms] fill-mode-both rounded-2xl bg-white/80 backdrop-blur-3xl border border-slate-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300`}>
              <div className="flex justify-between items-start mb-5">
                <h3 className="text-slate-500/90 font-semibold text-sm tracking-wide">{kpi.title}</h3>
                <div className={`p-2.5 rounded-xl ${kpi.bg}`}>{kpi.icon}</div>
              </div>
              <h2 className="text-4xl font-black tracking-tight text-slate-800 tracking-tight">{kpi.value}</h2>
              <p className="mt-3 text-sm font-medium text-slate-400">{kpi.change}</p>
            </div>
          ))}
        </div>

        {/* Charts & Graphs Row */}
        <div className={`grid grid-cols-1 ${viewMode === 'management' ? 'lg:grid-cols-3' : 'lg:grid-cols-1'} gap-6 print:hidden`}>

          {/* 12-Month Trajectory Area Chart */}
          <div className={`col-span-1 ${viewMode === 'management' ? 'lg:col-span-2' : ''} p-8 rounded-3xl bg-white/80 backdrop-blur-3xl border border-slate-100 shadow-sm`}>
            <div className="flex justify-between items-start mb-8">
              <div>
                <h2 className="text-xl print:text-sm font-bold text-slate-800">Revenue Trajectory Forecast</h2>
                <p className="text-sm font-medium text-slate-500/90 mt-1">Holt-Winters Statistical Bounds with Seasonal Detection</p>
              </div>
            </div>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={charts.areaData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="baselineColor" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#4f46e5" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="boundsColor" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#cbd5e1" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#cbd5e1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="4 4" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="month" stroke="#94a3b8" tick={{ fill: '#64748b', fontSize: 13, fontWeight: 500 }} axisLine={false} tickLine={false} dy={10} />
                  <YAxis stroke="#94a3b8" tick={{ fill: '#64748b', fontSize: 13, fontWeight: 500 }} axisLine={false} tickLine={false} tickFormatter={(value) => `₹${value / 1000}k`} dx={-10} />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '12px', color: '#0f172a', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                    itemStyle={{ color: '#334155', fontWeight: 600 }}
                    formatter={(value: any) => formatINR(value)}
                  />
                  <Area type="monotone" dataKey="upper" stroke="none" fill="url(#boundsColor)" />
                  <Area type="monotone" dataKey="lower" stroke="none" fill="#ffffff" />
                  <Area type="monotone" dataKey="baseline" stroke="#4f46e5" strokeWidth={4} fill="url(#baselineColor)" activeDot={{ r: 6, strokeWidth: 0, fill: '#4f46e5' }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Waterfall Chart */}
          {viewMode === 'management' && (
            <div className="col-span-1 p-8 rounded-3xl bg-white/80 backdrop-blur-3xl border border-slate-100 shadow-sm print:hidden">
              <div className="mb-8">
                <h2 className="text-xl print:text-sm font-bold text-slate-800">Current Variance</h2>
                <p className="text-sm font-medium text-slate-500/90 mt-1">EBITDA Bridge Breakdown</p>
              </div>
              <div className="h-80 w-full relative">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={charts.waterfallData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="4 4" stroke="#f1f5f9" vertical={false} />
                    <XAxis dataKey="name" stroke="#94a3b8" tick={{ fill: '#64748b', fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} dy={10} />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#64748b', fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} tickFormatter={(val) => `₹${val / 1000}k`} dx={-5} />
                    <RechartsTooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }} />
                    <Bar dataKey="value" radius={[6, 6, 6, 6]} barSize={40}>
                      {charts.waterfallData.map((entry: any, index: number) => {
                        if (entry.isTotal) return <Cell key={`cell-${index}`} fill="#94a3b8" />
                        if (entry.value > 0) return <Cell key={`cell-${index}`} fill="#10b981" />
                        return <Cell key={`cell-${index}`} fill="#f43f5e" />
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {/* --- CA ASSUMPTION SANDBOX (Scenario Planner) --- */}
        <div className="p-8 rounded-3xl bg-white/80 backdrop-blur-3xl border border-slate-200 shadow-sm print:hidden" data-export-hide>
          <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-100 pb-6">
            <div>
              <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-3">
                Scenario Stress Tester <span className="text-xs font-bold px-2 py-1 bg-indigo-100 text-indigo-700 rounded-md">PRO</span>
              </h2>
              <p className="text-slate-500/90 mt-2 font-medium">Override statistical ML bounds with management assumptions to test liquidity constraints.</p>
            </div>
            <button
              onClick={() => file && analyzeDocument(file)}
              className="px-6 py-3 print:px-2 print:py-1 bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-200 text-white text-sm font-bold rounded-xl transition-all active:scale-95"
            >
              Run Scenario
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 pt-2">
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase text-slate-500/90 tracking-wider">Revenue Growth Stress (%)</label>
              <input
                type="number"
                placeholder="e.g. 10 or -5"
                value={assumptions.revenue_growth}
                onChange={(e) => setAssumptions(prev => ({ ...prev, revenue_growth: e.target.value }))}
                className="bg-slate-50 border-2 border-slate-100 focus:border-indigo-500 focus:bg-white/80 backdrop-blur-3xl rounded-xl p-3.5 text-sm text-slate-800 font-semibold outline-none transition-colors"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase text-slate-500/90 tracking-wider">Effective Tax Bracket (%)</label>
              <input
                type="number"
                value={assumptions.tax_rate}
                onChange={(e) => setAssumptions(prev => ({ ...prev, tax_rate: e.target.value }))}
                className="bg-slate-50 border-2 border-slate-100 focus:border-indigo-500 focus:bg-white/80 backdrop-blur-3xl rounded-xl p-3.5 text-sm text-slate-800 font-semibold outline-none transition-colors"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase text-slate-500/90 tracking-wider">Planned CAPEX Injections (₹)</label>
              <input
                type="number"
                placeholder="e.g. 5000000"
                value={assumptions.new_capex}
                onChange={(e) => setAssumptions(prev => ({ ...prev, new_capex: e.target.value }))}
                className="bg-slate-50 border-2 border-slate-100 focus:border-indigo-500 focus:bg-white/80 backdrop-blur-3xl rounded-xl p-3.5 text-sm text-slate-800 font-semibold outline-none transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Advance Tax Notification */}
        {tax_metadata && (
          <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200 flex flex-col md:flex-row items-center justify-between gap-4 shadow-sm print:hidden">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-100 text-amber-600 rounded-lg">
                <CheckCircle2 size={24} />
              </div>
              <div>
                <h4 className="text-amber-900 font-bold text-sm">Section 211 Compliance Active</h4>
                <p className="text-amber-700/80 text-xs font-medium mt-0.5">Advance tax automatically staggered: Jun 15%, Sep 30%, Dec 30%, Mar 25%</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-amber-900 font-extrabold text-lg print:text-base">{formatINR(tax_metadata.estimated_annual_tax)}</p>
              <p className="text-amber-700/70 text-xs font-bold uppercase tracking-wider">Est. Annual Tax</p>
            </div>
          </div>
        )}

        {/* --- SCHEDULE III INDIRECT METHOD (AUDIT VIEW) --- */}
        {three_way_model && viewMode === 'schedule3' && (
          <div className="bg-white/80 backdrop-blur-3xl rounded-3xl border border-slate-200 shadow-sm overflow-hidden print:shadow-none print:border-none">
            <div className="p-10 border-b border-slate-200">
              <h2 className="text-2xl font-bold text-slate-800">Statement of Cash Flows</h2>
              <p className="text-slate-500/90 font-medium mt-1">Projected for the 12-month period ended March 31</p>
            </div>
            <div className="table-scroll-wrapper overflow-x-auto pb-4">
              <table className="w-full text-sm text-left align-middle border-collapse min-w-[1000px] print:min-w-0 print:text-[9.5px] print:leading-tight">
                <thead className="text-xs text-slate-500/90 uppercase bg-slate-50 border-b-2 border-slate-200">
                  <tr>
                    <th className="px-6 py-4 print:px-2 print:py-1.5 font-bold tracking-wider">Particulars</th>
                    {three_way_model.map((m: any) => (
                      <th key={`head-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 font-bold tracking-wider text-right">{m.month}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="tabular-nums">

                  {/* OPERATING ACTIVITIES */}
                  <tr className="bg-slate-50/50">
                    <td colSpan={13} className="px-6 py-4 print:px-2 print:py-1.5 font-extrabold text-indigo-700 text-sm tracking-wide">
                      A. Cash Flow from Operating Activities
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-semibold text-slate-800">Operating Profit before Working Capital Changes</td>
                    {three_way_model.map((m: any) => <td key={`opbwc-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-medium text-slate-800">{formatINR(m.operating_profit_bwc)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-2 print:px-2 print:py-0.5 text-slate-500/90 pl-10 text-xs font-medium uppercase tracking-wide">Adjustments for:</td>
                    <td colSpan={12}></td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-2 print:px-2 print:py-0.5.5 print:px-2 print:py-0.5 font-medium text-slate-600 pl-10">Trade and Other Receivables (Δ)</td>
                    {three_way_model.map((m: any) => <td key={`dar-${m.month}`} className="px-4 py-2.5 print:px-2 print:py-0.5 text-right text-slate-600">{formatINR(-m.delta_ar)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-2 print:px-2 print:py-0.5.5 print:px-2 print:py-0.5 font-medium text-slate-600 pl-10">Trade and Other Payables (Δ)</td>
                    {three_way_model.map((m: any) => <td key={`dap-${m.month}`} className="px-4 py-2.5 print:px-2 print:py-0.5 text-right text-slate-600">{formatINR(m.delta_ap)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-bold text-slate-800">Cash Generated from Operations</td>
                    {three_way_model.map((m: any) => <td key={`cfo-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-bold text-slate-800">{formatINR(m.cash_from_operations)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-200">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-rose-600 pl-10 tracking-tight">Less: Advance Taxes Paid</td>
                    {three_way_model.map((m: any) => <td key={`tax-${m.month}`} className={`px-4 py-3 print:px-2 print:py-1 text-right font-medium ${m.is_tax_quarter ? 'text-rose-600 font-bold bg-rose-50' : 'text-slate-400'}`}>{m.is_tax_quarter ? formatINR(-m.tax_liability) : '—'}</td>)}
                  </tr>
                  <tr className="border-b-2 border-slate-300 bg-indigo-50/50">
                    <td className="px-6 py-4 print:px-2 print:py-1.5 font-bold text-slate-800">Net Cash Flow from Operating Activities (A)</td>
                    {three_way_model.map((m: any) => <td key={`nco-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 text-right font-extrabold text-indigo-700">{formatINR(m.net_cash_operating)}</td>)}
                  </tr>

                  {/* INVESTING ACTIVITIES */}
                  <tr className="bg-slate-50/50">
                    <td colSpan={13} className="px-6 py-4 print:px-2 print:py-1.5 font-extrabold text-sky-700 text-sm tracking-wide mt-4">
                      B. Cash Flow from Investing Activities
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Capital Expenditure (PPE)</td>
                    {three_way_model.map((m: any) => <td key={`capex-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.net_cash_investing)}</td>)}
                  </tr>
                  <tr className="border-b-2 border-slate-300 bg-sky-50/50">
                    <td className="px-6 py-4 print:px-2 print:py-1.5 font-bold text-slate-800">Net Cash Used in Investing Activities (B)</td>
                    {three_way_model.map((m: any) => <td key={`nci-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 text-right font-extrabold text-sky-700">{formatINR(m.net_cash_investing)}</td>)}
                  </tr>

                  {/* FINANCING ACTIVITIES */}
                  <tr className="bg-slate-50/50">
                    <td colSpan={13} className="px-6 py-4 print:px-2 print:py-1.5 font-extrabold text-amber-700 text-sm tracking-wide mt-4">
                      C. Cash Flow from Financing Activities
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Repayment of Borrowings (Principal + Interest)</td>
                    {three_way_model.map((m: any) => <td key={`debt-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.net_cash_financing)}</td>)}
                  </tr>
                  <tr className="border-b-2 border-slate-300 bg-amber-50/50">
                    <td className="px-6 py-4 print:px-2 print:py-1.5 font-bold text-slate-800">Net Cash Used in Financing Activities (C)</td>
                    {three_way_model.map((m: any) => <td key={`ncf-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 text-right font-extrabold text-amber-700">{formatINR(m.net_cash_financing)}</td>)}
                  </tr>

                  {/* NET CASH MOVEMENT */}
                  <tr>
                    <td className="px-6 py-5 print:px-2 print:py-1.5 font-bold text-slate-800 text-base">Net Increase / (Decrease) in Cash (A+B+C)</td>
                    {three_way_model.map((m: any) => <td key={`ncflow-${m.month}`} className="px-4 py-5 print:px-2 print:py-1.5 text-right font-bold text-slate-800 text-base">{formatINR(m.net_cash_flow)}</td>)}
                  </tr>
                  <tr className="border-t border-slate-200">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-500/90">Opening Balance of Cash</td>
                    {three_way_model.map((m: any) => <td key={`open-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-medium text-slate-500/90">{formatINR(m.ending_cash - m.net_cash_flow)}</td>)}
                  </tr>
                  <tr className="border-t-2 border-slate-800 bg-slate-900 text-white">
                    <td className="px-6 py-5 print:px-2 print:py-1.5 font-bold uppercase tracking-wider rounded-bl-xl border-b-0">Closing Balance of Cash <span className="font-normal text-slate-400 normal-case ml-2">(Projected)</span></td>
                    {three_way_model.map((m: any) => (
                      <td key={`close-${m.month}`} className="px-4 py-5 print:px-2 print:py-1.5 text-right font-extrabold text-lg print:text-base border-b-0">
                        <span className="border-b-2 print:border-b border-double border-white pb-1">{formatINR(m.ending_cash)}</span>
                      </td>
                    ))}
                  </tr>

                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* --- MANAGEMENT VIEW (DIRECT METHOD + GRANULAR OPEX) --- */}
        {three_way_model && viewMode === 'management' && (
          <div className="bg-white/80 backdrop-blur-3xl rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-10 border-b border-slate-200 flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold text-slate-800">Direct Method Forecast</h2>
                <p className="text-slate-500/90 font-medium mt-1">Management overview with granular deep-dive capabilities</p>
              </div>
            </div>
            <div className="table-scroll-wrapper overflow-x-auto pb-4">
              <table className="w-full text-sm text-left align-middle border-collapse min-w-[1000px] print:min-w-0 print:text-[9.5px] print:leading-tight">
                <thead className="text-xs text-slate-500/90 uppercase bg-slate-50 border-b-2 border-slate-200">
                  <tr>
                    <th className="px-6 py-4 print:px-2 print:py-1.5 font-bold tracking-wider">Particulars</th>
                    {three_way_model.map((m: any) => <th key={`head-m-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 font-bold tracking-wider text-right">{m.month}</th>)}
                  </tr>
                </thead>
                <tbody className="tabular-nums">

                  {/* INFLOWS */}
                  <tr className="bg-slate-50/50">
                    <td colSpan={13} className="px-6 py-4 print:px-2 print:py-1.5 font-extrabold text-emerald-700 text-sm tracking-wide">CASH RECEIPTS (INFLOWS)</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-800 pl-10">Revenue / Sales Collection</td>
                    {three_way_model.map((m: any) => <td key={`rev-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-medium text-slate-800">{formatINR(m.revenue)}</td>)}
                  </tr>
                  <tr className="border-b-2 border-slate-300 bg-emerald-50/50">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-bold text-slate-800">Total Cash Receipts</td>
                    {three_way_model.map((m: any) => <td key={`trev-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-bold text-emerald-700">{formatINR(m.revenue)}</td>)}
                  </tr>

                  {/* OUTFLOWS */}
                  <tr className="bg-slate-50/50">
                    <td colSpan={13} className="px-6 py-4 print:px-2 print:py-1.5 font-extrabold text-rose-700 text-sm tracking-wide mt-4">CASH PAYMENTS (OUTFLOWS)</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Cost of Goods Sold (COGS)</td>
                    {three_way_model.map((m: any) => <td key={`cogs-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.cogs)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Salaries & Wages (Payroll)</td>
                    {three_way_model.map((m: any) => <td key={`pay-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.payroll)}</td>)}
                  </tr>

                  {/* Expandable Granular OpEx */}
                  <tr className={`border-b border-slate-100 transition-colors cursor-pointer hover:bg-slate-50 ${expandedOpex ? 'bg-slate-50' : ''}`} onClick={() => setExpandedOpex(!expandedOpex)}>
                    <td className="px-6 py-3 print:px-2 print:py-1 font-bold text-slate-800 pl-10 flex items-center gap-2">
                      {expandedOpex ? <Minus size={14} className="text-indigo-600" /> : <Plus size={14} className="text-indigo-600" />}
                      Total Operating Expenses (OpEx)
                    </td>
                    {three_way_model.map((m: any) => <td key={`opex-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right font-bold text-slate-800">{formatINR(m.opex)}</td>)}
                  </tr>

                  {/* The Granular Children */}
                  {expandedOpex && Object.keys(three_way_model[0]?.line_items || {}).map(lineItemKey => (
                    <tr key={lineItemKey} className="border-b border-slate-100 bg-slate-50/30">
                      <td className="px-6 py-2 print:px-2 print:py-0.5.5 print:px-2 print:py-0.5 font-medium text-slate-500/90 pl-16 flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div> {lineItemKey}
                      </td>
                      {three_way_model.map((m: any) => <td key={`li-${lineItemKey}-${m.month}`} className="px-4 py-2.5 print:px-2 print:py-0.5 text-right text-slate-500/90 text-xs">{formatINR(m.line_items[lineItemKey])}</td>)}
                    </tr>
                  ))}

                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Debt Service (EMI)</td>
                    {three_way_model.map((m: any) => <td key={`mdebt-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.debt)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-slate-600 pl-10">Capital Expenditure</td>
                    {three_way_model.map((m: any) => <td key={`mcapex-${m.month}`} className="px-4 py-3 print:px-2 print:py-1 text-right text-slate-600">{formatINR(m.capex)}</td>)}
                  </tr>
                  <tr className="border-b border-slate-200">
                    <td className="px-6 py-3 print:px-2 print:py-1 font-medium text-rose-600 pl-10">Section 211 Advance Tax</td>
                    {three_way_model.map((m: any) => <td key={`mtax-${m.month}`} className={`px-4 py-3 print:px-2 print:py-1 text-right font-medium ${m.is_tax_quarter ? 'text-rose-600 font-bold bg-rose-50' : 'text-slate-400'}`}>{m.is_tax_quarter ? formatINR(m.tax_liability) : '—'}</td>)}
                  </tr>

                  <tr className="border-b-2 border-slate-300 bg-rose-50/50">
                    <td className="px-6 py-4 print:px-2 print:py-1.5 font-bold text-slate-800">Total Cash Payments</td>
                    {three_way_model.map((m: any) => <td key={`totout-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 text-right font-bold text-rose-700">{formatINR(m.cogs + m.payroll + m.opex + m.debt + m.capex + m.tax_liability)}</td>)}
                  </tr>

                  <tr className="bg-slate-900 border-t border-slate-800 text-white">
                    <td className="px-6 py-4 print:px-2 print:py-1.5 font-bold text-lg print:text-base rounded-bl-xl border-b-0">Net Cash Flow</td>
                    {three_way_model.map((m: any) => <td key={`mncf-${m.month}`} className="px-4 py-4 print:px-2 print:py-1.5 text-right font-bold text-lg print:text-base border-b-0"><span className="border-b-2 border-white pb-1">{formatINR(m.net_cash_flow)}</span></td>)}
                  </tr>

                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
