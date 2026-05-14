import { useState, useCallback } from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useAuthStore } from "@/store/auth-store"
import type { DiscoveredCamera, DiscoveryStep } from "@/types"
import type { TestResult } from "./TestStep"
import { ScanStep } from "./ScanStep"
import { CredentialsStep } from "./CredentialsStep"
import { TestStep } from "./TestStep"
import { ResultsStep } from "./ResultsStep"

interface DiscoveryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete: () => void
}

const STEP_TITLES: Record<DiscoveryStep, string> = {
  scan: "Add Camera",
  credentials: "Camera Credentials",
  testing: "Testing & Saving...",
  results: "Setup Complete",
}

const STEP_DESCRIPTIONS: Record<DiscoveryStep, string> = {
  scan: "Scan your network or add a camera manually.",
  credentials: "Enter the camera's ONVIF credentials.",
  testing: "Validating connections and saving configuration.",
  results: "Review the results below.",
}

export function DiscoveryDialog({ open, onOpenChange, onComplete }: DiscoveryDialogProps) {
  const { shelterId } = useAuthStore()
  const [step, setStep] = useState<DiscoveryStep>("scan")
  const [selectedCameras, setSelectedCameras] = useState<DiscoveredCamera[]>([])
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [streamNames, setStreamNames] = useState<Map<string, string>>(new Map())
  const [testResults, setTestResults] = useState<TestResult[]>([])

  const isProcessing = step === "testing"

  const resetState = () => {
    setStep("scan")
    setSelectedCameras([])
    setUsername("")
    setPassword("")
    setStreamNames(new Map())
    setTestResults([])
  }

  const handleOpenChange = (newOpen: boolean) => {
    if (!isProcessing) {
      onOpenChange(newOpen)
      if (!newOpen) resetState()
    }
  }

  const handleScanComplete = useCallback((cameras: DiscoveredCamera[]) => {
    setSelectedCameras(cameras)
    setStep("credentials")
  }, [])

  const handleCredentialsSubmit = (
    user: string,
    pass: string,
    names: Map<string, string>,
  ) => {
    setUsername(user)
    setPassword(pass)
    setStreamNames(names)
    setStep("testing")
  }

  const handleTestComplete = useCallback((results: TestResult[]) => {
    setTestResults(results)
    setStep("results")
  }, [])

  const handleDone = () => {
    onOpenChange(false)
    resetState()
    onComplete()
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="sm:max-w-lg"
        onInteractOutside={(e) => {
          if (isProcessing) e.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle>{STEP_TITLES[step]}</DialogTitle>
          <DialogDescription>{STEP_DESCRIPTIONS[step]}</DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
          >
            {step === "scan" && shelterId && (
              <ScanStep
                shelterId={shelterId}
                onComplete={handleScanComplete}
                onClose={() => handleOpenChange(false)}
              />
            )}
            {step === "credentials" && (
              <CredentialsStep
                cameras={selectedCameras}
                onSubmit={handleCredentialsSubmit}
                onBack={resetState}
              />
            )}
            {step === "testing" && shelterId && (
              <TestStep
                cameras={selectedCameras}
                username={username}
                password={password}
                streamNames={streamNames}
                shelterId={shelterId}
                onComplete={handleTestComplete}
              />
            )}
            {step === "results" && (
              <ResultsStep
                results={testResults}
                onDone={handleDone}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  )
}
